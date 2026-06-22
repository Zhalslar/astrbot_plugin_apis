from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .log import get_logger
from .model import FieldCaster

logger = get_logger("database")


class SQLiteDatabase:
    """SQLite-backed storage for site/api pools."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.db_file = self.data_dir / "api_aggregator.db"
        self._init_schema()

        self.site_pool: list[dict[str, Any]] = []
        self.api_pool: list[dict[str, Any]] = []
        self.reload_from_database()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_file))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS site_pool (
                    pos INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_pool (
                    pos INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def _normalize_pool_data(data: Any) -> list[dict[str, Any]]:
        if not isinstance(data, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict):
                row = dict(item)
                if "enabled" not in row or row.get("enabled") is None:
                    row["enabled"] = True
                else:
                    row["enabled"] = FieldCaster.to_bool(
                        row.get("enabled"), default=True
                    )
                normalized.append(row)
        return normalized

    @classmethod
    def _normalize_upserts(cls, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("upserts must be a list")
        rows: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("upsert item must be an object")
            normalized = cls._normalize_pool_data([item])
            if not normalized:
                continue
            row = normalized[0]
            name = FieldCaster.normalize_name(row.get("name"))
            if not name:
                raise ValueError("upsert item missing name")
            row["name"] = name
            rows.append(row)
        return rows

    @classmethod
    def _normalize_delete_names(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            names = [value]
        elif isinstance(value, list):
            names = value
        else:
            raise ValueError("delete_names must be a string or list")
        result: list[str] = []
        seen: set[str] = set()
        for item in names:
            name = FieldCaster.normalize_name(item)
            if not name or name in seen:
                continue
            result.append(name)
            seen.add(name)
        return result

    @staticmethod
    def _write_pool_table(
        conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]
    ) -> None:
        conn.execute(f"DELETE FROM {table}")
        payload_rows = [
            (
                index,
                str(item.get("name", "")).strip(),
                json.dumps(item, ensure_ascii=False),
            )
            for index, item in enumerate(rows)
        ]
        if payload_rows:
            conn.executemany(
                f"INSERT INTO {table}(pos, name, payload) VALUES (?, ?, ?)",
                payload_rows,
            )

    @staticmethod
    def _load_table_pos_map(conn: sqlite3.Connection, table: str) -> dict[str, int]:
        rows = conn.execute(f"SELECT name, pos FROM {table}").fetchall()
        pos_map: dict[str, int] = {}
        for row in rows:
            name = FieldCaster.normalize_name(row["name"])
            if not name:
                continue
            try:
                pos_map[name] = int(row["pos"])
            except Exception:
                continue
        return pos_map

    @classmethod
    def _apply_pool_table_batch(
        cls,
        conn: sqlite3.Connection,
        table: str,
        *,
        upserts: list[dict[str, Any]],
        delete_names: list[str],
    ) -> None:
        if not upserts and not delete_names:
            return

        pos_map = cls._load_table_pos_map(conn, table)

        if delete_names:
            conn.executemany(
                f"DELETE FROM {table} WHERE name = ?",
                [(name,) for name in delete_names],
            )
            for name in delete_names:
                pos_map.pop(name, None)

        next_pos = (max(pos_map.values()) + 1) if pos_map else 0
        updates: list[tuple[str, str]] = []
        inserts: list[tuple[int, str, str]] = []
        for row in upserts:
            name = FieldCaster.normalize_name(row.get("name"))
            if not name:
                continue
            payload = json.dumps(row, ensure_ascii=False)
            if name in pos_map:
                updates.append((payload, name))
                continue
            inserts.append((next_pos, name, payload))
            pos_map[name] = next_pos
            next_pos += 1

        if updates:
            conn.executemany(
                f"UPDATE {table} SET payload = ? WHERE name = ?",
                updates,
            )
        if inserts:
            conn.executemany(
                f"INSERT INTO {table}(pos, name, payload) VALUES (?, ?, ?)",
                inserts,
            )

    def _save_pool_table(self, table: str, rows: list[dict[str, Any]]) -> None:
        try:
            with self._connect() as conn:
                self._write_pool_table(conn, table, rows)
                conn.commit()
        except Exception as exc:
            logger.error("save sqlite table failed (%s): %s", table, exc)

    @classmethod
    def _apply_pool_batch(
        cls,
        pool: list[dict[str, Any]],
        *,
        upserts: list[dict[str, Any]],
        delete_names: list[str],
    ) -> dict[str, Any]:
        delete_set = set(delete_names)
        updated = 0
        deleted = 0
        inserted = 0
        changed = False

        if delete_set:
            before = len(pool)
            pool[:] = [
                row
                for row in pool
                if FieldCaster.normalize_name(row.get("name")) not in delete_set
            ]
            deleted = before - len(pool)
            changed = deleted > 0

        index_by_name = {
            FieldCaster.normalize_name(row.get("name")): index
            for index, row in enumerate(pool)
            if FieldCaster.normalize_name(row.get("name"))
        }
        for row in upserts:
            name = FieldCaster.normalize_name(row.get("name"))
            if not name:
                continue
            index = index_by_name.get(name)
            if index is None:
                pool.append(row)
                index_by_name[name] = len(pool) - 1
                inserted += 1
                changed = True
            else:
                if pool[index] != row:
                    pool[index] = row
                    updated += 1
                    changed = True

        return {
            "changed": changed,
            "inserted": inserted,
            "updated": updated,
            "deleted": deleted,
            "total": len(pool),
        }

    def save_site_pool(self) -> None:
        self._save_pool_table("site_pool", self.site_pool)

    def save_api_pool(self) -> None:
        self._save_pool_table("api_pool", self.api_pool)

    def save_to_database(self) -> None:
        self.save_site_pool()
        self.save_api_pool()

    def batch_update_pools(
        self,
        *,
        site_upserts: list[dict[str, Any]] | None = None,
        site_delete_names: list[str] | str | None = None,
        api_upserts: list[dict[str, Any]] | None = None,
        api_delete_names: list[str] | str | None = None,
    ) -> dict[str, Any]:
        normalized_site_upserts = self._normalize_upserts(site_upserts)
        normalized_site_deletes = self._normalize_delete_names(site_delete_names)
        normalized_api_upserts = self._normalize_upserts(api_upserts)
        normalized_api_deletes = self._normalize_delete_names(api_delete_names)

        site_stats = self._apply_pool_batch(
            self.site_pool,
            upserts=normalized_site_upserts,
            delete_names=normalized_site_deletes,
        )
        api_stats = self._apply_pool_batch(
            self.api_pool,
            upserts=normalized_api_upserts,
            delete_names=normalized_api_deletes,
        )
        changed_tables: list[str] = []
        try:
            with self._connect() as conn:
                if site_stats["changed"]:
                    self._apply_pool_table_batch(
                        conn,
                        "site_pool",
                        upserts=normalized_site_upserts,
                        delete_names=normalized_site_deletes,
                    )
                    changed_tables.append("site_pool")
                if api_stats["changed"]:
                    self._apply_pool_table_batch(
                        conn,
                        "api_pool",
                        upserts=normalized_api_upserts,
                        delete_names=normalized_api_deletes,
                    )
                    changed_tables.append("api_pool")
                if changed_tables:
                    conn.commit()
        except Exception:
            self.reload_from_database()
            raise

        return {
            "changed_tables": changed_tables,
            "site": {k: v for k, v in site_stats.items() if k != "changed"},
            "api": {k: v for k, v in api_stats.items() if k != "changed"},
        }

    def batch_update_site_pool(
        self,
        *,
        upserts: list[dict[str, Any]] | None = None,
        delete_names: list[str] | str | None = None,
    ) -> dict[str, Any]:
        return self.batch_update_pools(
            site_upserts=upserts,
            site_delete_names=delete_names,
        )["site"]

    def batch_update_api_pool(
        self,
        *,
        upserts: list[dict[str, Any]] | None = None,
        delete_names: list[str] | str | None = None,
    ) -> dict[str, Any]:
        return self.batch_update_pools(
            api_upserts=upserts,
            api_delete_names=delete_names,
        )["api"]

    def reload_from_database(self) -> None:
        try:
            with self._connect() as conn:
                site_rows = conn.execute(
                    "SELECT payload FROM site_pool ORDER BY pos ASC"
                ).fetchall()
                api_rows = conn.execute(
                    "SELECT payload FROM api_pool ORDER BY pos ASC"
                ).fetchall()
        except Exception as exc:
            logger.error("load sqlite database failed: %s", exc)
            self.site_pool = []
            self.api_pool = []
            return

        self.site_pool = self._normalize_pool_data(
            [json.loads(str(row["payload"])) for row in site_rows]
        )
        self.api_pool = self._normalize_pool_data(
            [json.loads(str(row["payload"])) for row in api_rows]
        )

    @staticmethod
    def _to_page_size(value: Any) -> int | str:
        text = str(value).strip().lower()
        if not text or text == "all":
            return "all"
        try:
            size = int(text)
        except Exception:
            return 20
        return max(1, size)

    @staticmethod
    def _to_page(value: Any) -> int:
        try:
            page = int(str(value).strip())
        except Exception:
            return 1
        return max(1, page)

    @staticmethod
    def _paginate(
        items: list[dict[str, Any]], page: int, page_size: int | str
    ) -> dict[str, Any]:
        total = len(items)
        if page_size == "all":
            return {
                "items": items,
                "page": 1,
                "page_size": "all",
                "total": total,
                "total_pages": 1,
                "start": 1 if total else 0,
                "end": total,
            }
        size = max(1, int(page_size))
        total_pages = max(1, (total + size - 1) // size)
        safe_page = min(max(1, page), total_pages)
        start_index = (safe_page - 1) * size
        end_index = min(start_index + size, total)
        page_items = items[start_index:end_index]
        return {
            "items": page_items,
            "page": safe_page,
            "page_size": size,
            "total": total,
            "total_pages": total_pages,
            "start": start_index + 1 if total else 0,
            "end": end_index,
        }

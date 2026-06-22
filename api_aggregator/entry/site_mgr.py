from __future__ import annotations

from typing import Any

from ..database import SQLiteDatabase
from ..log import logger
from ..model import SitePayload
from .site_entry import SiteEntry


class SiteEntryManager:
    """Manage site entries and persistence mapping."""

    def __init__(self, db: SQLiteDatabase):
        self.db = db
        self.pool = self.db.site_pool
        self.entries: list[SiteEntry] = []

    async def initialize(self) -> None:
        # Support restart: rebuild in-memory entries from current pool state.
        stored_entries = [dict(item) for item in self.pool if isinstance(item, dict)]
        old_names = [
            str(item.get("name", "")).strip()
            for item in stored_entries
            if str(item.get("name", "")).strip()
        ]
        loaded: list[SiteEntry] = []
        normalized_rows: list[dict[str, Any]] = []
        dirty = False

        for item in stored_entries:
            try:
                entry = SiteEntry(item)
            except Exception as exc:
                logger.error(
                    "load site from database failed: %s -> %s",
                    item.get("name"),
                    exc,
                )
                dirty = True
                continue
            normalized = entry.to_dict()
            if normalized != item:
                dirty = True
            loaded.append(entry)
            normalized_rows.append(normalized)

        self.entries[:] = loaded
        self.pool[:] = normalized_rows

        # Persist only when load phase fixed/removed invalid rows.
        if dirty:
            self.db.batch_update_site_pool(
                upserts=normalized_rows,
                delete_names=old_names,
            )

    def _resolve_unique_name(self, name: str) -> str:
        if not self.get_entry(name):
            return name
        index = 2
        while True:
            new_name = f"{name}_{index}"
            if not self.get_entry(new_name):
                return new_name
            index += 1

    def _find_index(self, name: str) -> tuple[int, int]:
        cfg_idx = -1
        entry_idx = -1
        for i, item in enumerate(self.pool):
            if item.get("name") == name:
                cfg_idx = i
                break
        for i, entry in enumerate(self.entries):
            if entry.name == name:
                entry_idx = i
                break
        return cfg_idx, entry_idx

    @staticmethod
    def _normalize_payload(data: dict[str, Any]) -> dict[str, Any]:
        normalized = SitePayload.from_raw(
            data,
            require_name=True,
            require_url=True,
        ).to_dict()
        normalized.pop("template", None)
        normalized.pop("__template_key", None)
        return normalized

    def _build_entry_data(self, data: dict[str, Any]) -> dict[str, Any]:
        payload = SitePayload.from_raw(
            data,
            require_name=True,
            require_url=True,
        ).to_dict()
        entry_name = self._resolve_unique_name(payload["name"])
        return {
            "name": entry_name,
            "url": payload["url"],
            "enabled": payload["enabled"],
            "headers": payload["headers"],
            "keys": payload["keys"],
            "timeout": payload["timeout"],
        }

    def add_entries(
        self,
        payloads: list[dict[str, Any]],
        *,
        save: bool = True,
    ) -> list[SiteEntry]:
        if not isinstance(payloads, list) or not payloads:
            raise ValueError("payloads must be a non-empty list")
        created: list[SiteEntry] = []
        for raw in payloads:
            if not isinstance(raw, dict):
                raise ValueError("payload item must be an object")
            full_data = self._build_entry_data(raw)
            entry = SiteEntry(full_data)
            self.entries.append(entry)
            self.pool.append(full_data)
            created.append(entry)
        if save and created:
            self.db.batch_update_site_pool(
                upserts=[entry.to_dict() for entry in created]
            )
        return created

    def _update_entry(
        self,
        name: str,
        payload: dict[str, Any],
        *,
        save: bool,
    ) -> dict[str, Any]:
        idx_cfg, idx_entry = self._find_index(name)
        if idx_cfg < 0 or idx_entry < 0:
            raise LookupError(f"site not found: {name}")

        data = dict(self.pool[idx_cfg])
        data.update(payload)
        normalized = self._normalize_payload(data)
        new_name = str(normalized.get("name", ""))
        if new_name != name and self.get_entry(new_name):
            raise ValueError(f"site name already exists: {new_name}")

        self.pool[idx_cfg] = normalized
        self.entries[idx_entry] = SiteEntry(normalized)
        if save:
            self.db.batch_update_site_pool(upserts=[normalized])
        return dict(normalized)

    def update_entries(
        self,
        updates: list[dict[str, Any]],
        *,
        save: bool = True,
    ) -> list[dict[str, Any]]:
        changed: list[dict[str, Any]] = []
        for item in updates:
            if not isinstance(item, dict):
                raise ValueError("update item must be an object")
            name = str(item.get("name", "")).strip()
            payload = item.get("payload")
            if not name:
                raise ValueError("update item requires name")
            if not isinstance(payload, dict):
                raise ValueError("update item requires object payload")
            changed.append(self._update_entry(name, payload, save=False))
        if save and changed:
            self.db.batch_update_site_pool(upserts=changed)
        return changed

    def remove_entries(
        self,
        names: list[str],
        *,
        save: bool = True,
    ) -> tuple[list[str], list[str]]:
        success: list[str] = []
        failed: list[str] = []
        for name in names:
            normalized = str(name or "").strip()
            if not normalized:
                continue
            idx_cfg, idx_entry = self._find_index(normalized)
            if idx_cfg >= 0 and idx_entry >= 0:
                self.pool.pop(idx_cfg)
                self.entries.pop(idx_entry)
                success.append(normalized)
            else:
                failed.append(normalized)
        if save and success:
            self.db.batch_update_site_pool(delete_names=success)
        return success, failed

    @staticmethod
    def attach_api_counts(
        sites: list[dict[str, Any]], apis: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        count_by_site: dict[str, int] = {}
        for api in apis:
            site_name = str(api.get("site", "")).strip()
            if not site_name:
                continue
            count_by_site[site_name] = count_by_site.get(site_name, 0) + 1

        result: list[dict[str, Any]] = []
        for site in sites:
            row = dict(site)
            site_name = str(row.get("name", "")).strip()
            row["api_count"] = int(count_by_site.get(site_name, 0))
            result.append(row)
        return result

    def get_entry(self, name: str) -> SiteEntry | None:
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None

    def list_entries(self) -> list[SiteEntry]:
        return list(self.entries)

    def list_enabled_entries(self) -> list[SiteEntry]:
        return [entry for entry in self.entries if entry.enabled]

    def list_disabled_entries(self) -> list[SiteEntry]:
        return [entry for entry in self.entries if not entry.enabled]

    def match_entry(
        self,
        full_url: str,
        *,
        only_enabled: bool = True,
    ) -> SiteEntry | None:
        candidates = self.list_enabled_entries() if only_enabled else self.entries
        for entry in candidates:
            if entry.is_vested(full_url):
                return entry
        return None

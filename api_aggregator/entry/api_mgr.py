from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from ..database import SQLiteDatabase
from ..log import logger
from ..model import ApiPayload, DataType, FieldCaster
from .api_entry import APIEntry


class APIEntryManager:
    """Manage API entries and persistence mapping."""

    def __init__(self, db: SQLiteDatabase):

        self.db = db
        self.pool = self.db.api_pool
        self.entries: list[APIEntry] = []

    async def initialize(self) -> None:
        # Support restart: rebuild in-memory entries from current pool state.
        stored_entries = [dict(item) for item in self.pool if isinstance(item, dict)]
        old_names = [
            str(item.get("name", "")).strip()
            for item in stored_entries
            if str(item.get("name", "")).strip()
        ]
        loaded: list[APIEntry] = []
        normalized_rows: list[dict[str, Any]] = []
        dirty = False

        for item in stored_entries:
            try:
                entry = APIEntry(item)
            except Exception as exc:
                logger.error(
                    "load api from database failed: %s -> %s",
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
            self.db.batch_update_api_pool(
                upserts=normalized_rows,
                delete_names=old_names,
            )

    def get_entry(self, name: str) -> APIEntry | None:
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None

    def list_entries(self) -> list[APIEntry]:
        return list(self.entries)

    def list_entries_names(self) -> list[str]:
        return [entry.name for entry in self.entries]

    def list_enabled_entries(self) -> list[APIEntry]:
        return [entry for entry in self.entries if entry.enabled]

    def list_disabled_entries(self) -> list[APIEntry]:
        return [entry for entry in self.entries if not entry.enabled]

    def list_invalid_entries(self) -> list[APIEntry]:
        return [entry for entry in self.entries if not entry.valid]

    def list_valid_entries(self) -> list[APIEntry]:
        return [entry for entry in self.entries if entry.valid]

    def set_entries_valid(
        self,
        names: list[str],
        valid: bool,
    ) -> tuple[list[str], list[str]]:
        success: list[str] = []
        failed: list[str] = []
        changed = False
        dirty_names: set[str] = set()

        cfg_map = {cfg.get("name"): cfg for cfg in self.pool}
        for name in names:
            entry = self.get_entry(name)
            if not entry:
                failed.append(name)
                continue

            if entry.valid != valid:
                entry.valid = valid
                cfg = cfg_map.get(name)
                if isinstance(cfg, dict):
                    cfg["valid"] = valid
                changed = True
                dirty_names.add(name)
            success.append(name)

        if changed:
            changed_rows = [
                entry.to_dict() for entry in self.entries if entry.name in dirty_names
            ]
            self.db.batch_update_api_pool(upserts=changed_rows)

        return success, failed

    def match_entries(
        self,
        text: str,
        *,
        user_id: str = "",
        group_id: str = "",
        session_id: str = "",
        is_admin: bool = False,
        only_enabled: bool = True,
    ) -> list[APIEntry]:
        """Match entries by text and runtime context.

        Returns deep-copied entries so callers can safely mutate runtime params
        (for example `entry.updated_params`) without affecting manager state.
        """
        candidates = self.list_enabled_entries() if only_enabled else self.entries
        matched: list[APIEntry] = []
        for entry in candidates:
            if entry.check_activate(
                text=text,
                user_id=user_id,
                group_id=group_id,
                session_id=session_id,
                is_admin=is_admin,
            ):
                matched.append(copy.deepcopy(entry))
        return matched

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
    def _to_bool(value: Any, default: bool = True) -> bool:
        return FieldCaster.to_bool(value, default=default)

    @staticmethod
    def _to_dict(value: Any, default: dict[str, Any] | None = None) -> dict[str, Any]:
        return FieldCaster.to_dict(value, default=default)

    @staticmethod
    def _to_str_list(value: Any, default: list[str] | None = None) -> list[str]:
        return FieldCaster.to_str_list(value, default=default)

    def normalize_payload(
        self,
        payload: dict[str, Any],
        *,
        require_unique_name: bool,
        resolve_site_name: Callable[[str], str] | None = None,
    ) -> dict[str, Any]:
        normalized = ApiPayload.from_raw(
            payload,
            require_name=True,
            require_url=True,
            resolve_site_name=resolve_site_name,
        ).to_dict()
        name = normalized["name"]

        if require_unique_name and self.get_entry(name):
            raise ValueError(f"api name already exists: {name}")
        normalized.pop("template", None)
        normalized.pop("__template_key", None)
        return normalized

    def _build_entry_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = ApiPayload.from_raw(
            payload,
            require_name=True,
            require_url=True,
        ).to_dict()
        entry_name = self._resolve_unique_name(normalized["name"])
        return {
            "name": entry_name,
            "url": normalized["url"],
            "type": normalized["type"],
            "params": normalized["params"],
            "parse": normalized["parse"],
            "enabled": normalized["enabled"],
            "scope": normalized["scope"],
            "keywords": normalized["keywords"] or [entry_name],
            "valid": normalized["valid"],
            "site": normalized["site"],
        }

    def _update_one(
        self,
        name: str,
        payload: dict[str, Any],
        *,
        resolve_site_name: Callable[[str], str] | None = None,
    ) -> dict[str, Any]:
        idx_cfg, idx_entry = self._find_index(name)
        if idx_cfg < 0 or idx_entry < 0:
            raise LookupError(f"api not found: {name}")
        data = dict(self.pool[idx_cfg])
        data.update(payload)
        new_name = str(data.get("name", "")).strip()
        duplicate = self.get_entry(new_name)
        if new_name != name and duplicate:
            raise ValueError(f"api name already exists: {new_name}")
        normalized = self.normalize_payload(
            data,
            require_unique_name=False,
            resolve_site_name=resolve_site_name,
        )
        self.pool[idx_cfg] = normalized
        self.entries[idx_entry] = APIEntry(normalized)
        return dict(normalized)

    def sync_site_fields(self, resolve_site_name: Callable[[str], str]) -> bool:
        changed = False
        changed_rows: list[dict[str, Any]] = []
        for index, api_cfg in enumerate(self.pool):
            if not isinstance(api_cfg, dict):
                continue
            next_site = str(resolve_site_name(str(api_cfg.get("url", "")))).strip()
            if str(api_cfg.get("site", "")).strip() == next_site:
                continue
            api_cfg["site"] = next_site
            if index < len(self.entries):
                self.entries[index] = APIEntry(dict(api_cfg))
            changed_rows.append(dict(api_cfg))
            changed = True
        if changed:
            self.db.batch_update_api_pool(upserts=changed_rows)
        return changed

    def remove_entries(self, names: list[str]) -> tuple[list[str], list[str]]:
        success: list[str] = []
        failed: list[str] = []

        remaining_entries: list[APIEntry] = []
        remaining_configs: list[dict[str, Any]] = []
        name_set = set(names)

        for entry, cfg in zip(self.entries, self.pool):
            if entry.name in name_set:
                success.append(entry.name)
            else:
                remaining_entries.append(entry)
                remaining_configs.append(cfg)

        for name in names:
            if name not in success:
                failed.append(name)

        self.entries[:] = remaining_entries
        self.pool[:] = remaining_configs
        if success:
            self.db.batch_update_api_pool(delete_names=success)
        return success, failed

    def add_entries(
        self,
        payloads: list[dict[str, Any]],
        *,
        save: bool = True,
        emit_changed: bool = True,
    ) -> list[APIEntry]:
        created: list[APIEntry] = []
        for payload in payloads:
            if not isinstance(payload, dict):
                raise ValueError("payload item must be an object")
            full_data = self._build_entry_data(payload)
            entry = APIEntry(full_data)
            self.entries.append(entry)
            self.pool.append(full_data)
            created.append(entry)
        if save and created:
            self.db.batch_update_api_pool(
                upserts=[entry.to_dict() for entry in created]
            )
        return created

    def update_entries(
        self,
        updates: list[dict[str, Any]],
        *,
        resolve_site_name: Callable[[str], str] | None = None,
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
            changed.append(
                self._update_one(
                    name,
                    payload,
                    resolve_site_name=resolve_site_name,
                )
            )
        if save and changed:
            self.db.batch_update_api_pool(upserts=changed)
        return changed

    def add_scope_to_entry(self, name: str, scope: str) -> bool:
        entry = self.get_entry(name)
        if not entry:
            return False
        changed = entry.add_scope(scope)
        if changed:
            idx_cfg, _ = self._find_index(name)
            if idx_cfg >= 0:
                self.pool[idx_cfg]["scope"] = list(entry.scope)
            self.db.batch_update_api_pool(upserts=[entry.to_dict()])
        return True

    def remove_scope_from_entry(self, name: str, scope: str) -> bool:
        entry = self.get_entry(name)
        if not entry:
            return False
        changed = entry.remove_scope(scope)
        if changed:
            idx_cfg, _ = self._find_index(name)
            if idx_cfg >= 0:
                self.pool[idx_cfg]["scope"] = list(entry.scope)
            self.db.batch_update_api_pool(upserts=[entry.to_dict()])
        return True

    def update_keywords(self, name: str, keywords: list[str]) -> bool:
        entry = self.get_entry(name)
        if not entry:
            return False
        entry.set_keywords(keywords)
        idx_cfg, _ = self._find_index(name)
        if idx_cfg >= 0:
            self.pool[idx_cfg]["keywords"] = list(entry.keywords)
        self.db.batch_update_api_pool(upserts=[entry.to_dict()])
        return True

    def display_entries(self) -> str:
        if not self.entries:
            return "No API entries registered."
        api_types: dict[str, list[APIEntry]] = {t: [] for t in DataType.values()}
        api_types.setdefault("unknown", [])
        for entry in self.entries:
            api_type = entry.type or "unknown"
            api_types.setdefault(api_type, [])
            api_types[api_type].append(entry)

        lines = [f"---- total {len(self.entries)} APIs ----", ""]
        for api_type, items in api_types.items():
            if not items:
                continue
            lines.append(f"[{api_type}] {len(items)}:")
            lines.append(" | ".join(item.name for item in items))
            lines.append("")
        return "\n".join(lines).strip()

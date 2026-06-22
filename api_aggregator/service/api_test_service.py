from __future__ import annotations

import copy
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from ..data_service.local_data import LocalDataService
from ..data_service.remote_data import RemoteDataService
from ..data_service.request_result import RequestResult
from ..entry import APIEntry, APIEntryManager
from ..model import DataResource


class ApiTestService:
    """Compose API test flow, preview detail and persistence."""

    def __init__(
        self,
        remote: RemoteDataService,
        local: LocalDataService,
        api_mgr: APIEntryManager,
    ) -> None:
        self.remote = remote
        self.local = local
        self.api_mgr = api_mgr

    async def _persist_valid_result(
        self, entry: APIEntry, result: RequestResult
    ) -> None:
        data = DataResource(
            data_type=entry.data_type,
            name=entry.name,
            text=result.raw_text,
            binary=result.raw_content,
        )
        await self.local.save_data(data)

    async def stream_test_apis(
        self,
        names: list[str] | None = None,
        site_names: list[str] | None = None,
        query: str = "",
    ) -> AsyncIterator[dict[str, Any]]:
        selected_entries = self._select_entries(
            names=names or [],
            site_names=site_names or [],
            query=query,
        )
        base_entries = selected_entries or self.api_mgr.list_entries()
        entries = [self._with_runtime_test_defaults(entry) for entry in base_entries]

        async for event in self.remote.stream_test_apis(
            entries,
            persist_valid_result=self._persist_valid_result,
        ):
            yield event

    @staticmethod
    def _is_blank_runtime_value(value: Any) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    @staticmethod
    def _build_default_test_param(key: str) -> str:
        name = str(key or "").strip().lower()
        if not name:
            return "test"
        if "page" in name or "size" in name or name.endswith("id"):
            return "1"
        if "time" in name or "ts" in name or "timestamp" in name:
            return str(int(time.time() * 1000))
        return "test"

    @classmethod
    def _with_runtime_test_defaults(cls, entry: APIEntry) -> APIEntry:
        # Apply runtime-only defaults for blank params; do not mutate manager state.
        cloned = copy.deepcopy(entry)
        params = dict(cloned.params or {})
        filled: dict[str, Any] = {}
        for key, value in params.items():
            if cls._is_blank_runtime_value(value):
                filled[key] = cls._build_default_test_param(str(key))
        cloned.updated_params = filled
        return cloned

    def _select_entries(
        self,
        *,
        names: list[str],
        site_names: list[str],
        query: str,
    ) -> list[APIEntry] | None:
        normalized_names = [str(name).strip() for name in names if str(name).strip()]
        normalized_site_names = {
            str(site_name).strip() for site_name in site_names if str(site_name).strip()
        }
        normalized_query = str(query or "").strip().lower()

        has_scope = bool(normalized_names or normalized_site_names or normalized_query)
        if not has_scope:
            return None

        if normalized_names:
            selected: list[APIEntry] = []
            seen: set[str] = set()
            for name in normalized_names:
                if name in seen:
                    continue
                seen.add(name)
                entry = self.api_mgr.get_entry(name)
                if entry is not None:
                    selected.append(entry)
            base_entries = selected
        else:
            base_entries = self.api_mgr.list_entries()

        if normalized_site_names:
            base_entries = [
                entry
                for entry in base_entries
                if str(entry.site).strip() in normalized_site_names
            ]

        if normalized_query:
            base_entries = [
                entry
                for entry in base_entries
                if self._match_entry_query(entry, normalized_query)
            ]

        return base_entries

    @staticmethod
    def _match_entry_query(entry: APIEntry, query_text: str) -> bool:
        if not query_text:
            return True
        if query_text in str(entry.name).lower():
            return True
        if query_text in str(entry.url).lower():
            return True
        return any(
            query_text in str(keyword).lower() for keyword in (entry.keywords or [])
        )

    async def build_preview(
        self,
        payload: dict[str, Any],
        *,
        resolve_site_name: Callable[[str], str],
    ) -> dict[str, Any]:
        normalized = self.api_mgr.normalize_payload(
            payload,
            require_unique_name=False,
            resolve_site_name=resolve_site_name,
        )
        entry = self._with_runtime_test_defaults(APIEntry(normalized))
        result = await self.remote.get_data(entry)
        is_valid = result.is_valid()
        detail: dict[str, Any] = {
            "name": entry.name,
            "url": entry.url,
            "valid": is_valid,
            "is_duplicate": False,
            "status": result.status,
            "content_type": result.content_type or "",
            "final_url": result.final_url or "",
            "reason": self.remote._build_test_reason(result),
            "preview": self.remote._build_result_preview(result),
        }

        if is_valid:
            try:
                data = DataResource(
                    data_type=entry.data_type,
                    name=entry.name,
                    text=result.raw_text,
                    binary=result.raw_content,
                )
                saved = await self.local.save_data(data)
                detail["is_duplicate"] = bool(saved.is_duplicate)
                if detail["is_duplicate"]:
                    detail["duplicate_skipped"] = True
                    note = (
                        "duplicate data detected: skipped saving and reused local data"
                    )
                    reason_text = str(detail.get("reason", "")).strip()
                    detail["reason"] = (
                        f"{reason_text} | {note}" if reason_text else note
                    )
                if saved.saved_text is not None:
                    detail["saved_type"] = "text"
                    detail["saved_text"] = saved.saved_text
                    text_file = (
                        self.local.get_type_dir(entry.data_type)
                        / f"{entry.name}{entry.data_type.get_default_ext()}"
                    )
                    detail["saved_path"] = str(text_file)
                elif saved.saved_path is not None:
                    relative = saved.saved_path.resolve().relative_to(
                        self.local.local_dir.resolve()
                    )
                    rel_text = relative.as_posix()
                    detail["saved_type"] = entry.type
                    detail["saved_path"] = str(saved.saved_path)
                    detail["saved_file_path"] = rel_text
            except Exception as save_exc:
                note = f"save failed: {save_exc}"
                reason_text = str(detail.get("reason", "")).strip()
                detail["reason"] = f"{reason_text} | {note}" if reason_text else note
                detail["save_error"] = str(save_exc)
                detail["save_failed"] = True

        if self.api_mgr.get_entry(entry.name):
            self.api_mgr.set_entries_valid([entry.name], bool(detail["valid"]))

        return detail

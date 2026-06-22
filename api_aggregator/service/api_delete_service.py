from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..entry import APIEntryManager


@dataclass
class DeleteResult:
    ok: bool
    status: int
    message: str
    data: dict[str, Any]


class ApiDeleteService:
    """Handle explicit batch delete semantics."""

    def __init__(self, api_mgr: APIEntryManager) -> None:
        self.api_mgr = api_mgr

    @staticmethod
    def _result(
        ok: bool,
        status: int,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> DeleteResult:
        return DeleteResult(ok=ok, status=status, message=message, data=data or {})

    def delete_by_names(self, names: list[str]) -> DeleteResult:
        if not names:
            return self._result(False, 400, "missing api names")

        success, failed = self.api_mgr.remove_entries(names)
        data = {"requested": names, "deleted": success, "failed": failed}

        if not success:
            if len(names) == 1:
                missing = failed[0] if failed else names[0]
                return self._result(False, 404, f"api not found: {missing}")
            return self._result(False, 404, "no apis were deleted")

        return self._result(
            True,
            200,
            "apis deleted" if not failed else "apis deleted partially",
            data,
        )

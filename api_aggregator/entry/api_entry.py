from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from ..log import logger
from ..model import ApiPayload, DataType, FieldCaster


class APIEntry:
    """API entry."""

    @classmethod
    def _normalize_data(cls, data: dict[str, Any]) -> dict[str, Any]:
        normalized = ApiPayload.from_raw(
            data if isinstance(data, dict) else {},
            require_name=False,
            require_url=False,
        ).to_dict()
        return normalized

    def __init__(self, data: dict[str, Any]):
        normalized = self._normalize_data(data if isinstance(data, dict) else {})
        self.name = normalized["name"]
        self.url = normalized["url"]
        self.type = normalized["type"]
        self.params = dict(normalized["params"])
        self.parse = normalized["parse"]
        self.enabled = FieldCaster.to_bool(normalized["enabled"], default=True)
        self.scope = FieldCaster.to_str_list(normalized["scope"])
        self.keywords = FieldCaster.to_str_list(normalized["keywords"])
        self.valid = FieldCaster.to_bool(normalized["valid"], default=True)
        self.site = normalized["site"]
        try:
            self._data_type = DataType.from_str(self.type)
        except Exception:
            self.type = DataType.TEXT.value
            self._data_type = DataType.TEXT
        self._compiled_patterns: list[re.Pattern] = []
        self._compile_patterns()
        self.updated_params: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "name": self.name,
            "url": self.url,
            "type": self.type,
            "params": FieldCaster.to_dict(self.params),
            "parse": self.parse,
            "enabled": self.enabled,
            "scope": FieldCaster.to_str_list(self.scope),
            "keywords": FieldCaster.to_str_list(self.keywords),
            "valid": self.valid,
            "site": self.site,
        }

    @property
    def data_type(self) -> DataType:
        """Data type."""
        return self._data_type

    def get_base_url(self) -> str:
        """Get base URL."""
        parsed = urlparse(self.url)
        return (
            f"{parsed.scheme}://{parsed.netloc}"
            if parsed.scheme and parsed.netloc
            else self.url
        )

    # =============== Regex ===================

    def _compile_patterns(self) -> None:
        """Compile keyword regex patterns."""
        self._compiled_patterns.clear()
        if self.keywords:
            self.keywords = [k for k in self.keywords if k.strip()]

            for pattern in self.keywords:
                try:
                    self._compiled_patterns.append(re.compile(pattern))
                except re.error as e:
                    logger.warning(
                        f"[entry:{self.name}] regex compile failed: {pattern} ({e})"
                    )

    def set_keywords(self, keywords: list[str]) -> None:
        self.keywords = FieldCaster.to_str_list(keywords, default=[])
        self._compile_patterns()

    def add_scope(self, scope: str) -> bool:
        value = str(scope or "").strip()
        if not value:
            return False
        if value in self.scope:
            return False
        self.scope.append(value)
        return True

    def remove_scope(self, scope: str) -> bool:
        value = str(scope or "").strip()
        if not value:
            return False
        if value not in self.scope:
            return False
        self.scope = [item for item in self.scope if item != value]
        return True

    def _match_keywords(self, text: str) -> bool:
        """Whether any keyword regex matches."""
        for p in self._compiled_patterns:
            if p.search(text):
                return True
        return False

    # =============== Activation decision ==================

    def _allow_scope(
        self,
        *,
        user_id: str,
        group_id: str,
        session_id: str,
        is_admin: bool,
    ) -> bool:
        """Scope access gate."""
        if not self.scope:
            return True

        for s in self.scope:
            if s == "admin" and is_admin:
                return True
            if s == user_id:
                return True
            if s == group_id:
                return True
            if s == session_id:
                return True
        return False

    def check_activate(
        self,
        *,
        text: str,
        user_id: str,
        group_id: str,
        session_id: str,
        is_admin: bool,
    ) -> bool:
        """Unified activation check."""

        # Gate 1: global switch
        if not self.enabled:
            return False

        # Gate 2: validity
        if not self.valid:
            return False

        # Gate 3: scope gate
        if not self._allow_scope(
            user_id=user_id,
            group_id=group_id,
            session_id=session_id,
            is_admin=is_admin,
        ):
            return False

        # Gate 4: regex match
        if not self._match_keywords(text):
            return False

        return True

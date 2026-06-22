from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class FieldCaster:
    """Shared coercion helpers for request/entry normalization."""

    @staticmethod
    def to_bool(value: Any, *, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off", ""}:
                return False
        return bool(value)

    @staticmethod
    def to_dict(value: Any, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        return dict(default or {})

    @staticmethod
    def to_str_list(value: Any, *, default: list[str] | None = None) -> list[str]:
        if value is None:
            return list(default or [])
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else list(default or [])
        return list(default or [])

    @staticmethod
    def normalize_name(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def require_object_list(value: Any, *, field: str) -> list[dict[str, Any]]:
        if not isinstance(value, list) or not value:
            raise ValueError(f"field '{field}' must be a non-empty list")
        items = [item for item in value if isinstance(item, dict)]
        if not items:
            raise ValueError(f"field '{field}' must contain objects")
        return items

    @staticmethod
    def normalize_name_list(value: Any, *, field: str) -> list[str]:
        if isinstance(value, str):
            raw = [value]
        elif isinstance(value, list):
            raw = value
        else:
            raise ValueError(f"field '{field}' must be a string or list")
        names: list[str] = []
        seen: set[str] = set()
        for item in raw:
            name = FieldCaster.normalize_name(item)
            if not name or name in seen:
                continue
            names.append(name)
            seen.add(name)
        if not names:
            raise ValueError(f"field '{field}' must include at least one name")
        return names


@dataclass(frozen=True)
class ItemsBatch:
    items: list[dict[str, Any]]

    @classmethod
    def from_raw(
        cls,
        payload: dict[str, Any],
        *,
        field: str = "items",
    ) -> "ItemsBatch":
        return cls(
            items=FieldCaster.require_object_list(payload.get(field), field=field)
        )


@dataclass(frozen=True)
class NamesBatch:
    names: list[str]

    @classmethod
    def from_raw(
        cls,
        payload: dict[str, Any],
        *,
        field: str = "names",
    ) -> "NamesBatch":
        return cls(
            names=FieldCaster.normalize_name_list(payload.get(field), field=field)
        )


@dataclass(frozen=True)
class TargetsBatch:
    targets: list[dict[str, Any]]

    @classmethod
    def from_raw(
        cls, payload: dict[str, Any], *, field: str = "targets"
    ) -> "TargetsBatch":
        return cls(
            targets=FieldCaster.require_object_list(payload.get(field), field=field)
        )


@dataclass(frozen=True)
class UpdateItem:
    name: str
    payload: dict[str, Any]

    @classmethod
    def from_raw(cls, item: dict[str, Any]) -> "UpdateItem":
        name = FieldCaster.normalize_name(item.get("name"))
        payload = item.get("payload")
        if not name:
            raise ValueError("update item requires name")
        if not isinstance(payload, dict):
            raise ValueError("update item requires object payload")
        return cls(name=name, payload=dict(payload))


@dataclass(frozen=True)
class UpdateItemsBatch:
    items: list[UpdateItem]

    @classmethod
    def from_raw(
        cls,
        payload: dict[str, Any],
        *,
        field: str = "items",
    ) -> "UpdateItemsBatch":
        raw_items = FieldCaster.require_object_list(payload.get(field), field=field)
        return cls(items=[UpdateItem.from_raw(item) for item in raw_items])


@dataclass(frozen=True)
class SitePayload:
    name: str
    url: str
    enabled: bool
    headers: dict[str, Any]
    keys: dict[str, Any]
    timeout: int

    @classmethod
    def from_raw(
        cls,
        payload: dict[str, Any],
        *,
        require_name: bool = True,
        require_url: bool = True,
    ) -> "SitePayload":
        data = dict(payload)
        name = FieldCaster.normalize_name(data.get("name"))
        url = FieldCaster.normalize_name(data.get("url"))
        if require_name and not name:
            raise ValueError("site name is required")
        if require_url and not url:
            raise ValueError("site url is required")
        return cls(
            name=name,
            url=url,
            enabled=FieldCaster.to_bool(data.get("enabled"), default=True),
            headers=FieldCaster.to_dict(data.get("headers")),
            keys=FieldCaster.to_dict(data.get("keys")),
            timeout=int(data.get("timeout", 60)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "enabled": self.enabled,
            "headers": dict(self.headers),
            "keys": dict(self.keys),
            "timeout": self.timeout,
        }


@dataclass(frozen=True)
class ApiPayload:
    name: str
    url: str
    type: str
    params: dict[str, Any]
    parse: str
    enabled: bool
    scope: list[str]
    keywords: list[str]
    valid: bool
    site: str

    @classmethod
    def from_raw(
        cls,
        payload: dict[str, Any],
        *,
        require_name: bool = True,
        require_url: bool = True,
        resolve_site_name: Callable[[str], str] | None = None,
    ) -> "ApiPayload":
        data = dict(payload)
        name = FieldCaster.normalize_name(data.get("name"))
        url = FieldCaster.normalize_name(data.get("url"))
        if require_name and not name:
            raise ValueError("api name is required")
        if require_url and not url:
            raise ValueError("api url is required")

        keywords = FieldCaster.to_str_list(data.get("keywords"))
        site_name = (
            resolve_site_name(url)
            if resolve_site_name is not None
            else data.get("site")
        )
        return cls(
            name=name,
            url=url,
            type=str(data.get("type", "text")),
            params=FieldCaster.to_dict(data.get("params")),
            parse=str(data.get("parse", "")),
            enabled=FieldCaster.to_bool(data.get("enabled"), default=True),
            scope=FieldCaster.to_str_list(data.get("scope")),
            keywords=keywords or ([name] if name else []),
            valid=FieldCaster.to_bool(data.get("valid"), default=True),
            site=FieldCaster.normalize_name(site_name),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "type": self.type,
            "params": dict(self.params),
            "parse": self.parse,
            "enabled": self.enabled,
            "scope": list(self.scope),
            "keywords": list(self.keywords),
            "valid": self.valid,
            "site": self.site,
        }


class DataType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"

    # ===============================
    # Basic helpers
    # ===============================

    @classmethod
    def from_str(cls, value: str) -> "DataType":
        """Safely convert string to enum."""
        try:
            return cls(value.lower())
        except ValueError:
            raise ValueError(f"Unsupported data type: {value}")

    @classmethod
    def values(cls) -> list[str]:
        """Return all string values."""
        return [item.value for item in cls]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check whether the string value is valid."""
        return value.lower() in cls.values()

    # ===============================
    # Business helpers
    # ===============================
    @property
    def is_text(self) -> bool:
        """Whether it is text type."""
        return self == DataType.TEXT

    @property
    def is_image(self) -> bool:
        """Whether it is image type."""
        return self == DataType.IMAGE

    @property
    def is_video(self) -> bool:
        """Whether it is video type."""
        return self == DataType.VIDEO

    @property
    def is_audio(self) -> bool:
        """Whether it is audio type."""
        return self == DataType.AUDIO

    @property
    def is_binary(self) -> bool:
        """Whether it is a binary type."""
        return self in {DataType.IMAGE, DataType.VIDEO, DataType.AUDIO}

    def get_default_ext(self) -> str:
        """Return default file extension."""
        return {
            DataType.TEXT: ".json",
            DataType.IMAGE: ".jpg",
            DataType.VIDEO: ".mp4",
            DataType.AUDIO: ".mp3",
        }[self]

    def __str__(self) -> str:
        """User-friendly display."""
        return self.value


@dataclass
class DataResource:
    """Generic data resource."""

    data_type: DataType
    name: str

    # Input data
    text: str | None = None
    binary: bytes | None = None

    # Persisted results
    saved_text: str | None = None
    saved_path: Path | None = None
    is_duplicate: bool = False

    @property
    def final_text(self) -> str | None:
        return self.saved_text or self.text

    @property
    def final_bytes(self) -> bytes | Path | None:
        return self.saved_path or self.binary

    def validate_for_save(self) -> None:
        """Validate before saving."""
        if self.data_type.is_text and not self.text:
            raise ValueError("Text type requires text")

        if self.data_type.is_binary and not self.binary:
            raise ValueError("Binary type requires binary")

        if self.text and self.binary:
            raise ValueError("Cannot provide text and binary at the same time")

    def unlink(self) -> None:
        """Delete saved data and clear linkage."""
        if self.saved_path and self.saved_path.exists():
            try:
                self.saved_path.unlink()
                self.saved_path = None
            except Exception:
                pass

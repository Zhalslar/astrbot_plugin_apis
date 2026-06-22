import json
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup


@dataclass
class RequestResult:
    """Request result object."""

    status: int | None = None
    raw_text: str | None = None
    raw_content: bytes | None = None
    content_type: str | None = None
    error: str | None = None
    final_url: str | None = None

    # --------------------------
    # Basic properties
    # --------------------------

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def is_text(self) -> bool:
        return self.raw_text is not None

    @property
    def is_binary(self) -> bool:
        return self.raw_content is not None

    @property
    def text(self) -> str | None:
        return self.raw_text

    @property
    def content(self) -> bytes | None:
        return self.raw_content

    # --------------------------
    # Data processing logic
    # --------------------------

    def parse_nested(self, parse_rule: str):
        """Parse nested value from JSON payload."""
        if not self.raw_text:
            return self
        raw = self.raw_text.strip()
        if not (
            (raw.startswith("{") and raw.endswith("}"))
            or (raw.startswith("[") and raw.endswith("]"))
        ):
            return self

        try:
            data = json.loads(self.raw_text)
            value = self._get_nested_value(data, parse_rule)

            if isinstance(value, list):
                rendered_items: list[str] = []
                for item in value:
                    text = (
                        self.dict_to_string(item)
                        if isinstance(item, dict)
                        else str(item)
                    )
                    text = text.strip()
                    if text:
                        rendered_items.append(text)
                self.raw_text = "\n".join(rendered_items)
            elif isinstance(value, dict):
                self.raw_text = self.dict_to_string(value)
            else:
                self.raw_text = str(value)

        except Exception:
            pass

        return self

    def extract_html_text(self):
        """Extract plain text from HTML."""
        if self.raw_text and self.raw_text.strip().startswith("<!DOCTYPE html>"):
            soup = BeautifulSoup(self.raw_text, "html.parser")
            self.raw_text = soup.get_text(strip=True)
        return self

    def extract_urls(self, *, unique: bool = True) -> list[str]:
        """Extract URLs from response text."""
        if not self.raw_text:
            return []

        regex = re.compile(
            r'(https?://[^\s<>"{}|\\^`\[\]\')(),;]+\b)',
            re.IGNORECASE,
        )
        candidates = regex.findall(self.raw_text)

        valid, seen = [], set()

        for raw in candidates:
            raw = raw.strip("\"'")
            raw = unquote(raw)
            parsed = urlparse(raw)

            if parsed.scheme in {"http", "https"} and parsed.netloc:
                if unique and raw in seen:
                    continue
                if unique:
                    seen.add(raw)
                valid.append(raw)

        return valid

    def dict_to_string(self, input_dict) -> str:
        """
        Convert a dict into a formatted string with nested support.
        Each nested level increases indentation by two spaces.
        """

        def recursive_parse(d, level):
            result = ""
            indent = " " * (level * 2)  # indentation for current level
            for key, value in d.items():
                if isinstance(value, dict):  # recurse for nested dicts
                    result += f"{indent}{key}:\n"
                    result += recursive_parse(value, level + 1)
                elif isinstance(value, list):
                    for item in value:
                        result += "\n\n"
                        result += recursive_parse(item, level)
                else:
                    result += f"{indent}{key}: {value}\n"
            return result.strip()

        return recursive_parse(input_dict, 0)

    @staticmethod
    def _extract_nested_values(value: object, keys: list[str]) -> list[object]:
        if not keys:
            return [value]

        key = keys[0].strip("[]")
        rest = keys[1:]

        if isinstance(value, dict):
            if key == "" or key.isdigit():
                return []
            return RequestResult._extract_nested_values(value.get(key, ""), rest)

        if isinstance(value, list):
            if key == "":
                merged: list[object] = []
                for item in value:
                    merged.extend(RequestResult._extract_nested_values(item, rest))
                return merged
            if key.isdigit():
                index = int(key)
                if 0 <= index < len(value):
                    return RequestResult._extract_nested_values(value[index], rest)
                return []
            return []

        return []

    @staticmethod
    def _get_nested_value(result: object, target: str):
        keys = [key for key in re.split(r"\.|(\[\d*\])", target) if key and key.strip()]
        values = RequestResult._extract_nested_values(result, keys)
        if not values:
            return ""
        if len(values) == 1:
            return values[0]
        return values

    def is_valid(self) -> bool:
        """
        Determine whether this request result is business-valid.

        Rules:
        1. Network request must succeed (ok).
        2. HTTP status must be 2xx.
        3. Binary data is valid when length > 0.
        4. JSON:
            - Must be parseable.
            - If `code` exists and not in (0, 200), mark invalid.
            - If obvious error fields exist, mark invalid.
        5. HTML:
            - Must not contain common error keywords.
        6. Plain text:
            - Non-empty is considered valid.
        """

        # Network-level checks
        if not self.ok:
            return False

        if not self.status or not (200 <= self.status < 300):
            return False

        # Binary data
        if self.is_binary:
            return bool(self.raw_content and len(self.raw_content) > 0)

        # Text data must exist
        if not self.raw_text:
            return False

        text = self.raw_text.strip()
        if not text:
            return False

        content_type = (self.content_type or "").lower()

        # JSON checks
        if (
            "application/json" in content_type
            or (text.startswith("{") and text.endswith("}"))
            or (text.startswith("[") and text.endswith("]"))
        ):
            try:
                parsed = json.loads(text)
            except Exception:
                # Some APIs return plain text with JSON content-type.
                # Treat non-empty text as valid in this fallback path.
                return True

            if isinstance(parsed, dict):
                # ---- common code field checks ----
                code = parsed.get("code")
                if isinstance(code, int) and code not in (0, 200):
                    return False

                # ---- common error-field checks ----
                for key in ("error", "err", "message", "msg"):
                    val = parsed.get(key)
                    if isinstance(val, str):
                        lowered = val.lower()
                        if any(
                            kw in lowered
                            for kw in (
                                "error",
                                "invalid",
                                "fail",
                                "denied",
                                "unauthorized",
                                "forbidden",
                            )
                        ):
                            return False

            return True

        # HTML checks
        if "text/html" in content_type or "<html" in text.lower():
            lowered = text.lower()

            error_keywords = [
                "access denied",
                "forbidden",
                "unauthorized",
                "not found",
                "bad request",
                "service unavailable",
                "too many requests",
                "error 403",
                "error 404",
                "error 500",
            ]

            if any(k in lowered for k in error_keywords):
                return False

            return True

        # Plain text
        return True

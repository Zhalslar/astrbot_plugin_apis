from __future__ import annotations

from collections.abc import Iterable

from astrbot.core.message.components import Plain, Reply
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


async def get_nickname(event: AstrMessageEvent, target_id: str) -> str:
    """Get nickname from platform when available."""
    if isinstance(event, AiocqhttpMessageEvent):
        info = await event.bot.get_stranger_info(user_id=int(target_id))
        return info.get("nickname") or info.get("nick") or target_id
    return target_id


def get_reply_text(event: AstrMessageEvent) -> str:
    """Get plain text from quoted message chain."""
    text = ""
    chain = event.get_messages()
    reply_seg = next((seg for seg in chain if isinstance(seg, Reply)), None)
    if reply_seg and reply_seg.chain:
        for seg in reply_seg.chain:
            if isinstance(seg, Plain):
                text = seg.text
    return text


def _build_session(
    platform_id: str,
    message_type: MessageType,
    session_id: str,
) -> str:
    return str(MessageSession(platform_id, message_type, session_id))


def _try_parse_full_session(value: str) -> str | None:
    try:
        session = MessageSession.from_str(value)
        return str(session)
    except Exception:
        return None


def _dedupe_keep_order(items: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _normalize_admin_ids(admin_ids: Iterable[object] | None) -> list[str]:
    if not admin_ids:
        return []
    values: list[str] = []
    for item in admin_ids:
        text = str(item).strip()
        if not text:
            continue
        values.append(text)
    return _dedupe_keep_order(values)


def resolve_cron_target_sessions(
    scope: Iterable[object] | None,
    *,
    default_platform_id: str | None,
    admin_ids: Iterable[object] | None = None,
) -> list[str]:
    """Resolve API scope values to AstrBot message sessions.

    Rules:
    - Full session string `platform:MessageType:session_id` is used as-is.
    - `admin` expands to all configured admin user IDs as private sessions.
    - `group:<id>` uses group session.
    - `user:<id>` / `private:<id>` uses private session.
    - bare `<id>` defaults to private session.
    - Invalid values are ignored.
    """

    if not scope:
        return []

    if not default_platform_id:
        return []

    normalized_admin_ids = _normalize_admin_ids(admin_ids)
    sessions: list[str] = []

    for raw in scope:
        if not isinstance(raw, str):
            continue

        text = raw.strip()
        if not text:
            continue

        lowered = text.lower()

        if lowered == "admin":
            for admin_id in normalized_admin_ids:
                sessions.append(
                    _build_session(
                        default_platform_id,
                        MessageType.FRIEND_MESSAGE,
                        admin_id,
                    )
                )
            continue

        # Try strict full-session parsing first.
        full_session = _try_parse_full_session(text)
        if full_session is not None:
            sessions.append(full_session)
            continue

        if ":" in text:
            prefix, value = text.split(":", 1)
            target_id = value.strip()
            if not target_id:
                continue

            prefix_lower = prefix.strip().lower()
            if prefix_lower == "group":
                sessions.append(
                    _build_session(
                        default_platform_id,
                        MessageType.GROUP_MESSAGE,
                        target_id,
                    )
                )
                continue

            if prefix_lower in {"user", "private"}:
                sessions.append(
                    _build_session(
                        default_platform_id,
                        MessageType.FRIEND_MESSAGE,
                        target_id,
                    )
                )
                continue

            if prefix_lower == "admin":
                sessions.append(
                    _build_session(
                        default_platform_id,
                        MessageType.FRIEND_MESSAGE,
                        target_id,
                    )
                )
                continue

            # Unknown prefix: ignore for tolerance.
            continue

        # Bare ID defaults to private message target.
        sessions.append(
            _build_session(
                default_platform_id,
                MessageType.FRIEND_MESSAGE,
                text,
            )
        )

    return _dedupe_keep_order(sessions)

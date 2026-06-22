from __future__ import annotations

from astrbot.core.message.components import Plain, Reply
from astrbot.core.platform.astr_message_event import AstrMessageEvent
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

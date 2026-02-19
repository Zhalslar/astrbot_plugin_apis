import base64
from pathlib import Path
from typing import Any

from api_aggregator import APICoreApp, APIEntry, DataResource

import astrbot.core.message.components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.star.filter.event_message_type import EventMessageType
from astrbot.core.utils.astrbot_path import (
    get_astrbot_plugin_data_path,
    get_astrbot_plugin_path,
)

from .utils import get_nickname, get_reply_text, resolve_cron_target_sessions


class APIPlugin(Star):
    """
    API插件
    """

    _plugin_name = "astrbot_plugin_apis"

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.admin_ids = self.context.get_config().get("admins_id", [])
        self.data_dir = Path(get_astrbot_plugin_data_path()) / self._plugin_name
        self.plugin_dir = Path(get_astrbot_plugin_path()) / self._plugin_name
        self.presets_dir = self.plugin_dir / "presets"
        self.api_pool_file = self.presets_dir / "api_pool_default.json"
        self.site_pool_file = self.presets_dir / "site_pool_default.json"

        self.core = APICoreApp(data_dir=self.data_dir)
        self.core.set_cron_entry_handler(self.on_entry_cron_trigger)

    async def initialize(self):
        await self.core.start()
        self._load_presets()

    async def terminate(self):
        await self.core.stop()

    def _load_presets(self):
        if self.config["load_presets"]:
            try:
                self.core.load_api_pool_from_file(self.api_pool_file)
                self.core.load_site_pool_from_file(self.site_pool_file)
                self.config["load_presets"] = False
                self.config.save_config()
            except Exception as e:
                logger.error(f"加载预设失败: {e}")

    @staticmethod
    async def data_to_comp(data: DataResource) -> Comp.BaseMessageComponent:
        data_type = data.data_type
        if data_type.is_text and data.final_text:
            return Comp.Plain(data.final_text)

        if data_type.is_image:
            if data.saved_path:
                return Comp.Image.fromFileSystem(str(data.saved_path))
            if data.binary:
                return Comp.Image.fromBytes(data.binary)
            raise ValueError("missing image payload")

        if data_type.is_video:
            if data.saved_path:
                return Comp.Video.fromFileSystem(str(data.saved_path))
            raise ValueError("missing video payload")

        if data_type.is_audio:
            if data.saved_path:
                return Comp.Record.fromFileSystem(str(data.saved_path))
            if data.binary:
                encoded = base64.b64encode(data.binary).decode("utf-8")
                return Comp.Record.fromBase64(encoded)
            raise ValueError("missing audio payload")

        raise ValueError(f"unsupported data type: {data.data_type}")

    async def _build_params(
        self, event: AstrMessageEvent, entry: APIEntry, args: list[str]
    ) -> dict[str, Any]:
        params = entry.params or {}
        keys = list(params.keys())
        updated_params = dict(params)
        if not keys:
            return updated_params

        def is_empty(value: Any) -> bool:
            return value is None or (isinstance(value, str) and value.strip() == "")

        remaining_args = [value for value in args if value not in (None, "")]

        # 1) Fill empty params first.
        if remaining_args:
            for key in keys:
                if not remaining_args:
                    break
                if is_empty(updated_params.get(key)):
                    updated_params[key] = remaining_args.pop(0)

        # 2) Force overwrite in param order with leftover args.
        if remaining_args:
            for i, value in enumerate(remaining_args):
                if i >= len(keys):
                    break
                updated_params[keys[i]] = value

        if not any(is_empty(updated_params.get(key)) for key in keys):
            return updated_params

        extra_args: list[str] = []
        reply_text = get_reply_text(event)
        if reply_text:
            extra_args = [item for item in reply_text.strip().split() if item]

        if not extra_args:
            sender_id = str(event.get_sender_id() or "")
            if sender_id:
                nickname = await get_nickname(event, sender_id)
                if nickname:
                    extra_args = [nickname]

        # 3) Fill remaining empty params from reply/nickname fallback.
        for value in extra_args:
            if value in (None, ""):
                continue
            for key in keys:
                if is_empty(updated_params.get(key)):
                    updated_params[key] = value
                    break
            else:
                break

        return updated_params

    # ================ API commands =================

    @filter.command("查看api")
    async def api_detail(self, event: AstrMessageEvent, api_name: str | None = None):
        if api_name:
            entry = self.core.api_mgr.get_entry(api_name)
            if entry:
                msg = entry.to_dict()
                yield event.plain_result(str(msg))
                return
        yield event.plain_result(self.core.api_mgr.display_entries())

    @filter.event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        if self.config["need_prefix"] and not event.is_at_or_wake_command:
            return

        msg = event.message_str
        if not msg:
            return

        parts = msg.split()
        cmd = parts[0]
        args = parts[1:]

        entries = self.core.api_mgr.match_entries(
            cmd,
            user_id=event.get_sender_id(),
            group_id=event.get_group_id(),
            session_id=event.unified_msg_origin,
            is_admin=event.is_admin(),
        )
        if not entries:
            return

        for entry in entries:
            entry.updated_params = await self._build_params(event, entry, args)
            try:
                data = await self.core.data_service.fetch(
                    entry,
                    use_local=self.config["use_local"],
                )
            except Exception as exc:
                logger.error(f"data processing failed for {entry.name}: {exc}")
                continue
            if data is None:
                continue

            try:
                comp = await self.data_to_comp(data)
            except Exception as exc:
                logger.error(f"data processing failed: {exc}")
                continue

            yield event.chain_result([comp])

            if not self.config["save_data"]:
                data.unlink()

    async def on_entry_cron_trigger(self, entry: APIEntry) -> None:
        data = await self.core.fetch_cron_data(
            entry, use_local=self.config["use_local"]
        )
        if data is None:
            return

        try:
            platform_insts = self.context.platform_manager.platform_insts
            default_platform_id = (
                platform_insts[0].meta().id if platform_insts else None
            )
            sessions = resolve_cron_target_sessions(
                entry.scope,
                default_platform_id=default_platform_id,
                admin_ids=self.admin_ids,
            )
            if not sessions:
                logger.warning(
                    f"[cron] entry {entry.name} has no valid target in scope"
                )
                return

            comp = await self.data_to_comp(data)
            sent_count = 0
            for session in sessions:
                try:
                    await self.context.send_message(session, MessageChain([comp]))
                    sent_count += 1
                except Exception as exc:
                    logger.error(
                        f"[cron] send failed for {entry.name} -> {session}: {exc}"
                    )
            logger.debug(
                f"[cron] send done: entry={entry.name}, targets={len(sessions)}, sent={sent_count}"
            )
        finally:
            if not self.config["save_data"]:
                data.unlink()

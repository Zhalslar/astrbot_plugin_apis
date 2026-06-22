import base64
from typing import Any

import astrbot.core.message.components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.filter.event_message_type import EventMessageType

from .api_aggregator import APICoreApp, APIEntry, DataResource
from .config import PluginConfig
from .page_controller import APIPageController
from .utils import get_nickname, get_reply_text


class APIPlugin(Star):
    _plugin_name = "astrbot_plugin_apis"

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        self.core = APICoreApp(self.cfg)
        self.page_controller = APIPageController(context, self.core)
        self.page_controller.register_routes()

    async def initialize(self):
        await self.core.start()
        self._load_presets()

    async def terminate(self):
        await self.core.stop()

    def _load_presets(self):
        try:
            if not self.core.site_mgr.entries:
                self.core.load_site_pool_from_file(self.cfg.site_pool_file)
            if not self.core.api_mgr.entries:
                self.core.load_api_pool_from_file(self.cfg.api_pool_file)
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

    @filter.command("查看api", aliases=["查看api列表", "api列表"])
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
        if self.cfg.need_prefix and not event.is_at_or_wake_command:
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

        event.should_call_llm(True)
        for entry in entries:
            entry.updated_params = await self._build_params(event, entry, args)
            try:
                data = await self.core.data_service.fetch(
                    entry,
                    use_local=self.cfg.use_local,
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

            if not self.cfg.save_data:
                data.unlink()

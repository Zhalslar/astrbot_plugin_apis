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

    @staticmethod
    def _format_api_entry_summary(entry: APIEntry) -> str:
        """Build a compact one-line summary for an API entry.

        Args:
            entry: API entry to summarize.

        Returns:
            One readable line for list display.
        """
        params = ", ".join(entry.params.keys()) if entry.params else "-"
        return f"{entry.name} | type={entry.type} | params={params}"

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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("启用api")
    async def enable_api(self, event: AstrMessageEvent, api_name: str | None = None):
        """启用api <api名称>"""
        target_name = str(api_name or "").strip()
        if not target_name:
            yield event.plain_result("未指定 API 名称")
            return
        entry = self.core.api_mgr.get_entry(target_name)
        if entry is None:
            yield event.plain_result(f"未找到 API：{target_name}")
            return
        if entry.enabled:
            yield event.plain_result(f"API 已处于启用状态：{target_name}")
            return
        self.core.api_mgr.update_entries(
            [{"name": target_name, "payload": {"enabled": True}}],
            resolve_site_name=self.core.site_sync_service.resolve_api_site_name,
        )
        yield event.plain_result(f"已启用 API：{target_name}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("禁用api")
    async def disable_api(self, event: AstrMessageEvent, api_name: str | None = None):
        """禁用api <api名称>"""
        target_name = str(api_name or "").strip()
        if not target_name:
            yield event.plain_result("未指定 API 名称")
            return
        entry = self.core.api_mgr.get_entry(target_name)
        if entry is None:
            yield event.plain_result(f"未找到 API：{target_name}")
            return
        if not entry.enabled:
            yield event.plain_result(f"API 已处于禁用状态：{target_name}")
            return
        self.core.api_mgr.update_entries(
            [{"name": target_name, "payload": {"enabled": False}}],
            resolve_site_name=self.core.site_sync_service.resolve_api_site_name,
        )
        yield event.plain_result(f"已禁用 API：{target_name}")

    @filter.llm_tool()
    async def query_available_apis(
        self,
        event: AstrMessageEvent,
        query: str = "",
    ) -> str:
        """Use this first when the user wants some API-provided content but has not given an exact API name.(Support: text, picture, video, audio)

        Search by intent, topic, content type, or rough keyword to find candidate APIs, then choose one API name for calling.

        Args:
            query(string): Optional search text for narrowing candidates.

        Returns:
            A short candidate list, or compact detail when query is an exact API name.
        """
        query_text = str(query or "").strip()
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        session_id = event.unified_msg_origin
        is_admin = event.is_admin()

        accessible_entries: list[APIEntry] = []
        for entry in self.core.api_mgr.list_enabled_entries():
            if entry.scope:
                allowed = False
                for scope in entry.scope:
                    if scope == "admin" and is_admin:
                        allowed = True
                        break
                    if scope == user_id or scope == group_id or scope == session_id:
                        allowed = True
                        break
                if not allowed:
                    continue
            accessible_entries.append(entry)

        if not accessible_entries:
            return "No accessible APIs are available in the current context."

        if query_text:
            exact_entry = next(
                (entry for entry in accessible_entries if entry.name == query_text),
                None,
            )
            if exact_entry is not None:
                params = (
                    ", ".join(exact_entry.params.keys()) if exact_entry.params else "-"
                )
                return "\n".join(
                    [
                        f"API: {exact_entry.name}",
                        f"Type: {exact_entry.type}",
                        f"Params: {params}",
                        f"Site: {exact_entry.site or '-'}",
                    ]
                )

        filtered_entries: list[APIEntry] = []
        if query_text:
            query_lower = query_text.lower()
            for entry in accessible_entries:
                params_text = " ".join(entry.params.keys())
                keywords_text = " ".join(entry.keywords)
                haystack = " ".join(
                    [
                        entry.name,
                        entry.site,
                        entry.type,
                        params_text,
                        keywords_text,
                    ]
                ).lower()
                if query_lower in haystack or entry.check_activate(
                    text=query_text,
                    user_id=user_id,
                    group_id=group_id,
                    session_id=session_id,
                    is_admin=is_admin,
                ):
                    filtered_entries.append(entry)
        else:
            filtered_entries = accessible_entries

        if not filtered_entries:
            return f"No accessible API matched query: {query_text}"

        shown_entries = filtered_entries[:30]
        lines = [f"Accessible APIs: {len(filtered_entries)}"]
        for entry in shown_entries:
            lines.append(f"- {self._format_api_entry_summary(entry)}")
        if len(filtered_entries) > len(shown_entries):
            lines.append(f"... and {len(filtered_entries) - len(shown_entries)} more.")
        lines.append(
            "Use the exact API name with call_api_by_name when you want to invoke one."
        )
        return "\n".join(lines)

    @filter.llm_tool()
    async def call_api_by_name(
        self,
        event: AstrMessageEvent,
        api_name: str,
        args_text: str = "",
    ) -> str:
        """Use this when you already know the exact API name and want to execute it now.

        If the user wants API-provided content but no exact API name is known yet, call query_available_apis first.

        Args:
            api_name(string): Exact API name. Query first if you are unsure.
            args_text(string): Optional plain arguments used to fill params.

        Returns:
            Text content for text APIs, or a short delivery summary after sending media.
        """
        target_name = str(api_name or "").strip()
        if not target_name:
            return "API call failed: api_name is required."

        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        session_id = event.unified_msg_origin
        is_admin = event.is_admin()

        source_entry = self.core.api_mgr.get_entry(target_name)
        if source_entry is not None:
            if not source_entry.check_activate(
                text=source_entry.name,
                user_id=user_id,
                group_id=group_id,
                session_id=session_id,
                is_admin=is_admin,
            ):
                return (
                    "API call failed: the API is not accessible in the current context."
                )
            entry = APIEntry(source_entry.to_dict())
        else:
            matched_entries = self.core.api_mgr.match_entries(
                target_name,
                user_id=user_id,
                group_id=group_id,
                session_id=session_id,
                is_admin=is_admin,
            )
            if not matched_entries:
                return (
                    f"API call failed: API not found or not accessible: {target_name}"
                )
            if len(matched_entries) > 1:
                candidate_names = ", ".join(item.name for item in matched_entries[:10])
                return (
                    "API call failed: api_name is ambiguous. "
                    f"Candidates: {candidate_names}"
                )
            entry = matched_entries[0]

        args = [item for item in str(args_text or "").split() if item]
        entry.updated_params = await self._build_params(event, entry, args)

        try:
            data = await self.core.data_service.fetch(
                entry,
                use_local=self.cfg.use_local,
            )
        except Exception as exc:
            logger.error(f"llm api call failed for {entry.name}: {exc}")
            return f"API call failed: {exc}"

        if data is None:
            return f"API call failed: no data returned for {entry.name}."

        if data.data_type.is_text and data.final_text:
            return data.final_text

        try:
            comp = await self.data_to_comp(data)
        except Exception as exc:
            logger.error(f"llm api result conversion failed for {entry.name}: {exc}")
            return f"API call failed: result conversion failed: {exc}"

        await event.send(event.chain_result([comp]))  # type: ignore[arg-type]

        if not self.cfg.save_data:
            data.unlink()

        return (
            f"API call succeeded: sent {data.data_type.value} result for {entry.name}."
        )

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

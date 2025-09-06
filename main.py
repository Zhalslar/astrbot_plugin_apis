import os
from pathlib import Path
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.filter.event_message_type import EventMessageType
from astrbot.core.message.components import (
    BaseMessageComponent,
    Image,
    Plain,
    Record,
    Video,
)
from .core.local import LocalDataManager
from .core.api_manager import APIManager
from .core.utils import get_nickname
from .core.request import RequestManager


@register(
    "astrbot_plugin_apis",
    "Zhalslar",
    "API聚合插件，海量免费API动态添加，热门API：看看腿、看看腹肌...",
    "v2.0.2",
    "https://github.com/Zhalslar/astrbot_plugin_apis",
)
class APIsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config
        # 启用的 API 类型
        self.enable_api_type = [
            k[7:] for k, v in config.get("type_switch", {}).items() if v
        ]
        # 本地数据存储路径
        self.local_data_dir = StarTools.get_data_dir("astrbot_plugin_apis")
        # api数据文件
        self.system_api_file = Path(__file__).parent / "system_api.json"
        self.user_api_file = self.local_data_dir / "user_api.json"

    async def initialize(self):
        self.local = LocalDataManager(self.local_data_dir)
        self.api = APIManager(self.system_api_file, self.user_api_file)
        self.apis_names = self.api.get_apis_names()
        self.web = RequestManager(self.conf, self.api)

    @staticmethod
    async def data_to_chain(
        api_type: str, text: str | None = "", path: str | Path | None = ""
    ) -> list[BaseMessageComponent]:
        """根据数据类型构造消息链"""
        chain = []
        if api_type == "text" and text:
            chain = [Plain(text)]

        elif api_type == "image" and path:
            chain = [Image.fromFileSystem(str(path))]

        elif api_type == "video" and path:
            chain = [Video.fromFileSystem(str(path))]

        elif api_type == "audio" and path:
            chain = [Record.fromFileSystem(str(path))]

        return chain  # type: ignore

    async def _supplement_args(self, event: AstrMessageEvent, args: list, params: dict):
        """
        补充参数逻辑
        :param event: 事件对象
        :param args: 当前参数列表（可能为空）
        :param params: 参数字典
        :return: 更新后的 args 和 params
        """
        # 尝试从回复消息中提取参数
        if not args:
            reply_seg = next(
                (seg for seg in event.get_messages() if isinstance(seg, Comp.Reply)),
                None,
            )
            if reply_seg and reply_seg.chain:
                for seg in reply_seg.chain:
                    if isinstance(seg, Comp.Plain):
                        args = seg.text.strip().split(" ")
                        break

        # 如果仍未获取到参数，尝试从 @ 消息中提取昵称
        if not args:
            for seg in event.get_messages():
                if isinstance(seg, Comp.At):
                    seg_qq = str(seg.qq)
                    if seg_qq != event.get_self_id():
                        nickname = await get_nickname(event, seg_qq)
                        if nickname:
                            args.append(nickname)
                            break
        # 如果仍未获取到参数，尝试使用发送者名称作为额外参数
        if not args:
            extra_arg = event.get_sender_name()
            params = {
                key: extra_arg if not value else value for key, value in params.items()
            }

        return args, params

    @filter.command("api列表")
    async def api_list(self, event: AstrMessageEvent, api_name: str | None = None):
        """api详情 <api名称> 不填名称则返回所有api信息"""
        api_info = self.api.list_api()
        yield event.plain_result(api_info)

    @filter.command("api详情")
    async def api_detail(self, event: AstrMessageEvent, api_name: str | None = None):
        """api详情 <api名称> 不填名称则返回所有api信息"""
        if not api_name:
            yield event.plain_result("未指定api名称")
            return
        api_detail = self.api.get_detail(api_name)
        yield event.plain_result(api_detail)

    @filter.command("添加api")
    async def api_add(self, event: AstrMessageEvent):
        api_detail = event.message_str.removeprefix("添加api").strip()
        try:
            data = self.api.from_detail_str(api_detail)
            self.api.add_api(data)
            yield event.plain_result(f"添加api成功:\n{data}")
        except Exception as e:
            logger.error(e)
            yield event.plain_result("添加api失败, 请检查格式，务必与 api详情 的输出数据格式一致")


    @filter.command("删除api")
    async def remove_api(self, event: AstrMessageEvent, api_name: str):
        """删除api"""
        self.api.remove_api(api_name)
        yield event.plain_result(f"已删除api：{api_name}")

    @filter.command("api测试")
    async def api_status(self, event: AstrMessageEvent):
        """轮询所有api, 测试api可用性"""
        yield event.plain_result(f"正在轮询{len(self.api.apis.keys())}个api，请稍等...")
        abled, disabled = await self.web.batch_test_apis()
        msg = (
            f"【可用的API】\n{', '.join(abled)}\n\n【失效的API】\n{', '.join(disabled)}"
        )
        yield event.plain_result(f"{msg}")

    @filter.event_message_type(EventMessageType.ALL)
    async def match_api(self, event: AstrMessageEvent):
        """主函数"""

        # 前缀模式
        if self.conf["prefix_mode"] and not event.is_at_or_wake_command:
            return

        # 匹配api
        msgs = event.message_str.split(" ")
        data = self.api.match_api_by_name(msgs[0])
        if not data:
            return

        # 检查api是否被禁用
        if data["name"] in self.conf["disable_apis"]:
            logger.debug("此API已被禁用")
            return

        # 检查该站点是否被禁用
        for url in data["urls"]:
            for site in self.conf["disable_sites"]:
                if url.startswith(site):
                    logger.debug(f"此站点已被禁用：{url}")
                    return

        # 检查api类型是否被禁用
        if data["type"] not in self.enable_api_type:
            logger.debug("此API类型已被禁用")
            return

        # 获取参数
        args = msgs[1:]

        # 参数补充
        args, params = await self._supplement_args(event, args, data["params"])

        # 生成update_params，保留params中的默认值
        update_params = {
            key: args[i] if i < len(args) else params[key]
            for i, key in enumerate(params.keys())
        }

        try:
            # === 外部接口调用 ===
            api_text, api_byte = await self.web.get_data(
                urls=data["urls"],
                params=update_params,
                api_type=data["type"],
                target=data["target"],
            )
            if api_text or api_byte:
                saved_text, saved_path = await self.local.save_data(
                    api_type=data["type"],
                    path_name=data["name"],
                    text=api_text,
                    byte=api_byte,
                )
                chain = await self.data_to_chain(
                    api_type=data["type"], text=saved_text, path=saved_path
                )
                await event.send(event.chain_result(chain))
                event.stop_event()
                if saved_path and not self.conf["auto_save_data"]:
                    os.remove(saved_path)
                return

        except Exception as e:
            logger.error(f"调用 API {data['name']} 失败: {e}")
            if self.conf.get("debug"):
                await event.send(
                    event.plain_result(f"调用API [{data['name']}] 失败: {e}")
                )

        # === 本地兜底 ===
        logger.debug("API响应为空，尝试从本地数据库中获取数据")
        try:
            local_text, local_path = await self.local.get_data(
                api_type=data["type"], path_name=data["name"]
            )
            chain = await self.data_to_chain(
                api_type=data["type"], text=local_text, path=local_path
            )
            await event.send(event.chain_result(chain))
            event.stop_event()
        except Exception as e:
            logger.error(f"本地兜底失败: {e}")
            if self.conf.get("debug"):
                await event.send(
                    event.plain_result(f"本地兜底 [{data['name']}] 失败: {e}")
                )

    async def terminate(self):
        """关闭会话，断开连接"""
        await self.web.terminate()
        logger.info("已关闭astrbot_plugin_image_apis的网络连接")

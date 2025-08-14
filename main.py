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
    "v2.0.0",
    "https://github.com/Zhalslar/astrbot_plugin_apis",
)
class ArknightsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # 前缀
        self.wake_prefix: list[str] = self.context.get_config().get("wake_prefix", [])
        # 是否启用前缀模式
        self.prefix_mode = config.get("prefix_mode", False)
        # 是否开启调试模式
        self.debug = config.get("debug", False)
        # 是否保存数据
        self.auto_save_data = config.get("auto_save_data", False)
        # 启用的 API 类型
        self.enable_api_type = [
            k[7:] for k, v in config.get("type_switch", {}).items() if v
        ]
        # 禁用的api列表
        self.disable_api = config.get("disable_api", [])
        # 本地数据存储路径
        self.local_data_dir = StarTools.get_data_dir("astrbot_plugin_apis")
        # api数据文件
        self.api_file = Path(__file__).parent / "api_data.json"

    async def initialize(self):
        self.web = RequestManager()
        self.local = LocalDataManager(self.local_data_dir)
        self.api = APIManager(self.api_file)
        self.apis_names = self.api.get_apis_names()

    @staticmethod
    async def data_to_chain(
        data_type: str, text: str | None = "", path: str | Path | None = ""
    ) -> list[BaseMessageComponent]:
        """根据数据类型构造消息链"""
        chain = []
        if data_type == "text" and text:
            chain = [Plain(text)]

        elif data_type == "image" and path:
            chain = [Image.fromFileSystem(str(path))]

        elif data_type == "video" and path:
            chain = [Video.fromFileSystem(str(path))]

        elif data_type == "audio" and path:
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
    async def api_ls(self, event: AstrMessageEvent):
        """
        根据API字典生成分类字符串,即api列表。
        """
        # 初始化分类字典
        api_types = {"text": [], "image": [], "video": [], "audio": []}

        # 遍历apis字典，按type分类
        for key, value in self.api.apis.items():
            api_type = value.get("type", "unknown")
            if api_type in api_types:
                api_types[api_type].append(key)

        # 生成最终字符串
        result = f"----共收录了{len(self.api.apis)}个API----\n\n"
        for api_type in api_types:
            if api_types[api_type]:
                result += f"【{api_type}】{len(api_types[api_type])}个：\n"
                for key in api_types[api_type]:
                    result += f"{key}、"
            result += "\n\n"

        yield event.plain_result(result.strip())

    @filter.command("api详情")
    async def api_help(self, event: AstrMessageEvent, api_name: str | None = None):
        """查看api的详细信息"""
        api_info = self.api.get_api_info(api_name)

        # 构造参数字符串
        params = api_info.get("params", {})
        params_list = [
            f"{key}={value}" if value is not None and value != "" else key
            for key, value in params.items()
        ]
        params_str = ",".join(params_list) if params_list else "无"

        api_str = (
            f"api匹配词：{api_info.get('keyword') or '无'}\n"
            f"api地址：{api_info.get('url') or '无'}\n"
            f"api类型：{api_info.get('type') or '无'}\n"
            f"所需参数：{params_str}\n"
            f"解析路径：{api_info.get('target') or '无'}"
        )
        yield event.plain_result(api_str)

    @filter.command("删除api")
    async def remove_api(self, event: AstrMessageEvent, api_name: str):
        """删除api"""
        self.api.remove_api(api_name)
        yield event.plain_result(f"已删除api：{api_name}")

    @filter.event_message_type(EventMessageType.ALL)
    async def match_api(self, event: AstrMessageEvent):
        """主函数"""

        # 前缀模式
        if self.prefix_mode and not event.is_at_or_wake_command:
            return

        # 匹配api
        message_str = event.get_message_str()
        msgs = message_str.split(" ")
        result = self.api.match_api_by_name(msgs[0])
        if not result:
            return
        api_name, api_data = result

        # 检查api是否被禁用
        if api_name in self.disable_api:
            logger.debug("此API已被禁用")
            return

        url: str | list = api_data.get("url", "")
        fuzzy: bool = api_data.get("fuzzy", False)
        type: str = api_data.get("type", "image")
        params: dict = api_data.get("params", {})
        target: str = api_data.get("target", "")

        # 检查api类型是否启用
        if type not in self.enable_api_type:
            logger.debug("此API类型已被禁用")
            return

        # 获取参数
        args = msgs[1:]

        # 参数补充
        args, params = await self._supplement_args(event, args, params)

        # 生成update_params，保留params中的默认值
        update_params = {
            key: args[i] if i < len(args) else params[key]
            for i, key in enumerate(params.keys())
        }
        if self.debug:
            logger.debug(
                "向API发送请求所用的参数:\n"
                f"url: {url}\n"
                f"fuzzy: {fuzzy}\n"
                f"update_params: {update_params}\n"
                f"type: {type}\n"
                f"target: {target}"
            )

        # 发送请求
        api_text, api_byte = await self.web.get_data(
            url=url, params=update_params, data_type=type, target=target
        )
        if api_text or api_byte:
            saved_text, saved_path = await self.local.save_data(
                data_type=type, path_name=api_name, text=api_text, byte=api_byte
            )
            chain = await self.data_to_chain(
                data_type=type, text=saved_text, path=saved_path
            )
            await event.send(event.chain_result(chain))
            event.stop_event()
            # 删除临时文件
            if saved_path and not self.auto_save_data:
                os.remove(saved_path)
            return

        # 如果响应为空，尝试从本地数据库中获取数据
        else:
            logger.warning("API响应为空，尝试从本地数据库中获取数据")
            local_text, local_path = await self.local.get_data(
                data_type=type, path_name=api_name
            )
            if local_text or local_path:
                chain = await self.data_to_chain(
                    data_type=type, text=local_text, path=local_path
                )
                await event.send(event.chain_result(chain))
                event.stop_event()
                return
            else:
                logger.error(f"‘{api_name}’的本地数据为空")


    async def terminate(self):
        """关闭会话，断开连接"""
        if self.web:
            await self.web.terminate()
            logger.info("已关闭astrbot_plugin_image_apis的网络连接")

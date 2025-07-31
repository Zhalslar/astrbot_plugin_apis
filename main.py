import asyncio
import json
import os
from pathlib import Path
import random
import re
from typing import Any, List, Optional, Union
from urllib.parse import unquote, urlparse
import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import BaseMessageComponent
from astrbot.core.star.filter.event_message_type import EventMessageType
from data.plugins.astrbot_plugin_apis.api_manager import APIManager


# 定义缓存路径
DATA_PATH = Path("./data/plugins_data/astrbot_plugin_apis")
DATA_PATH.mkdir(parents=True, exist_ok=True)

# 定义子路径
TYPE_DIRS = {
    "text": DATA_PATH / "text",
    "image": DATA_PATH / "image",
    "video": DATA_PATH / "video",
    "audio": DATA_PATH / "audio",
}


api_file = (
    Path(__file__).parent / "api_data.json"
)  # api_data.json 文件路径，更新插件时会被覆盖


@register(
    "astrbot_plugin_apis",
    "Zhalslar",
    "API聚合插件，海量免费API动态添加，热门API：看看腿、看看腹肌...",
    "1.0.8",
    "https://github.com/Zhalslar/astrbot_plugin_apis",
)
class ArknightsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.wake_prefix: list[str] = self.context.get_config().get("wake_prefix", [])
        self.prefix_mode = config.get("prefix_mode", False)  # 是否启用前缀模式
        self.API = APIManager(api_file=api_file)
        self.apis_names = self.API.get_apis_names()
        self.debug = config.get("debug", False)  # 是否开启调试模式
        self.auto_save_data = config.get("auto_save_data", False)  # 是否保存数据
        self.enable_api_type = [
            k[7:] for k, v in config.get("type_switch", {}).items() if v
        ]
        self.disable_api = config.get("disable_api", [])  # 禁用的api列表

    @filter.command("api列表")
    async def api_ls(self, event: AstrMessageEvent):
        """
        根据API字典生成分类字符串,即api列表。
        """
        # 初始化分类字典
        api_types = {"text": [], "image": [], "video": [], "audio": []}

        # 遍历apis字典，按type分类
        for key, value in self.API.apis.items():
            api_type = value.get("type", "unknown")
            if api_type in api_types:
                api_types[api_type].append(key)

        # 生成最终字符串
        result = f"----共收录了{len(self.API.apis)}个API----\n\n"
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
        api_info = self.API.get_api_info(api_name)

        # 构造参数字符串
        params = api_info.get("params", {})
        params_list = [
            f"{key}={value}" if value is not None and value != "" else key
            for key, value in params.items()
        ]
        params_str = ",".join(params_list) if params_list else "无"

        api_str = (
            f"api名称：{api_info.get('name') or '无'}\n"
            f"api地址：{api_info.get('url') or '无'}\n"
            f"api类型：{api_info.get('type') or '无'}\n"
            f"所需参数：{params_str}\n"
            f"解析路径：{api_info.get('target') or '无'}"
        )
        yield event.plain_result(api_str)

    @filter.command("添加api")
    async def add_api(
        self,
        event: AstrMessageEvent,
        input_name: str | None = None,
        input_url: str | None = None,
        input_type: str | None = None,
        input_params: str | None = None,
        input_target: str | None = None,
    ):
        """添加api"""

        def _extract_value(input_str: str | None) -> str:
            if input_str:
                parts = input_str.split("：", 1)  # 使用中文冒号分割
                if len(parts) == 2:
                    if parts[1].strip() == "无":
                        return ""
                    return parts[1].strip()
            return ""

        # 解析参数字符串为字典
        def _parse_params(params_str: str) -> dict:
            params = {}
            if params_str:
                pairs = params_str.split(",")
                for pair in pairs:
                    key_value = pair.split("=", 1)
                    if len(key_value) == 2:
                        key, value = key_value
                        params[key.strip()] = value.strip() if value.strip() else ""
                    else:
                        params[pair.strip()] = None
            return params

        # 预处理输入参数
        if self.debug:
            logger.debug(
                f"原始输入：\n{input_name}\n{input_url}\n{input_type}\n{input_params}\n{input_target}\n\n"
            )

        name = _extract_value(input_name)
        url = _extract_value(input_url)
        type_ = _extract_value(input_type)
        params_str = _extract_value(input_params)
        target = _extract_value(input_target)

        params = _parse_params(params_str)

        if self.debug:
            logger.debug(
                f"处理后的参数：\n{name}\n{url}\n{type_}\n{params}\n{target}\n"
            )

        if name in self.disable_api:
            yield event.plain_result("该API已被禁用")
            return

        # API是否重复
        if self.API.check_duplicate_api(name):
            yield event.plain_result("API已存在，将自动覆盖")

        # 构造 api_info
        api_info = {
            "name": name,
            "url": url,
            "type": type_,
            "params": params,
            "target": target,
        }

        # 将 api_info 添加到 API 管理器中
        self.API.add_api(api_info)

        # 返回确认消息
        yield event.plain_result(f"【{api_info['name']}】API添加成功: \n{api_info}")

    @filter.command("删除api")
    async def remove_api(self, event: AstrMessageEvent, api_name: str):
        """删除api"""
        self.API.remove_api(api_name)
        yield event.plain_result(f"已删除api：{api_name}")

    async def _make_request(
        self, url: str, params: Optional[dict] = None
    ) -> Union[bytes, str, dict, None]:
        """
        发送GET请求（异步版本）

        :param url: 请求的URL地址
        :param params: 请求参数，默认为None
        :return: 响应对象或None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url=url, params=params, timeout=30) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "").lower()
                    if "application/json" in content_type:
                        if self.debug:
                            logger.debug("类型：json")
                        return await response.json()
                    elif "text/html" in content_type or "text/plain" in content_type:
                        if self.debug:
                            logger.debug("类型：text")
                        return (await response.text()).strip()
                    else:
                        if self.debug:
                            logger.debug("类型：bytes")
                        return await response.read()
        except aiohttp.ClientResponseError as http_err:
            logger.error(f"HTTP请求出错: {http_err}")
        except aiohttp.ClientConnectionError as conn_err:
            logger.error(f"连接错误: {conn_err}")
        except asyncio.TimeoutError as timeout_err:
            logger.error(f"请求超时: {timeout_err}")
        except Exception as e:
            logger.error(f"请求异常: {e}")

    @filter.event_message_type(EventMessageType.ALL)
    async def match_api(self, event: AstrMessageEvent):
        """主函数"""

        # 前缀模式
        if self.prefix_mode:
            chain = event.get_messages()
            if not chain:
                return
            first_seg = chain[0]
            # 前缀触发
            if isinstance(first_seg, Comp.Plain):
                if not any(first_seg.text.startswith(prefix) for prefix in self.wake_prefix):
                    return
            # @bot触发
            elif isinstance(first_seg, Comp.At):
                if str(first_seg.qq) != str(event.get_self_id()):
                    return
            else:
                return


        # 匹配api
        message_str = event.get_message_str()
        msgs = message_str.split(" ")
        result = self.API.match_api_by_name(msgs[0])
        if not result:
            return
        api_name, api_data = result

        # 检查api是否被禁用
        if api_name in self.disable_api:
            logger.debug("此API已被禁用")
            return

        url: str = api_data.get("url", "")
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
                f"update_params: {update_params}\n"
                f"type: {type}\n"
                f"target: {target}"
            )

        data = None

        # 发送请求
        data = await self._make_request(url=url, params=update_params)
        if self.debug:
            logger.debug(f"响应结果: {data}")
        if data:
            chain = await self._process_api_data(
                data=data,
                api_name=api_name,
                data_type=type,
                target=target,
                auto_save_data=self.auto_save_data
            )
            try:
                await event.send(event.chain_result(chain))
                return
            except Exception as e:
                # TODO 等框架提供发送消息失败时提供反馈
                logger.error(f"在发送消息时发生错误: {e}")

        # 如果响应为空，尝试从本地数据库中获取数据
        else:
            logger.warning("API响应为空，尝试从本地数据库中获取数据")
            data = await self._get_data(path_name=api_name, data_type=type)
            if data:
                chain = await self._process_local_data(
                    data=data,
                    data_type=type,
                )
                await event.send(event.chain_result(chain))
                logger.info( f"发送本地数据成功: {data}")
            else:
                logger.error(f"没有找到本地数据: {api_name}")

        # 停止事件传播
        if data:
            event.stop_event()


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
                        nickname = await self._get_extra(event, seg_qq)
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

    async def _process_api_data(
        self,
        api_name: str,
        data: Any,
        data_type: str,
        target: str = "",
        auto_save_data: bool = True,
    ) -> List[BaseMessageComponent]:
        """处理响应"""
        chain = []
        text = None
        file_path = None

        # data为字典时，解析字典
        if isinstance(data, dict) and target:
            nested_value = self._get_nested_value(data, target)
            if isinstance(nested_value, dict):
                data = self._dict_to_string(nested_value)
            else:
                data = nested_value

        # 保存数据
        if isinstance(data, (str, bytes)):
            save_data: str | Path | None = await self._save_data(
                data, api_name, data_type
            )
            if not save_data:
                text = "数据为空"
            elif isinstance(save_data, str):
                text = save_data
            elif isinstance(save_data, Path):
                file_path = str(save_data)

        # 根据类型构造消息链
        if data_type == "text" and text:
            chain = [Comp.Plain(text)]

        elif data_type == "image" and file_path:
            chain = [Comp.Image.fromFileSystem(file_path)]

        elif data_type == "video" and file_path:
            chain = [Comp.Video.fromFileSystem(file_path)]

        elif data_type == "audio" and file_path:
            chain = [Comp.Record.fromFileSystem(file_path)]

        # 删除临时文件
        if isinstance(data, bytes) and file_path and not auto_save_data:
            os.remove(file_path)

        return chain  # type: ignore

    async def _process_local_data(
        self,
        data: Any,
        data_type: str,
    ) -> List[BaseMessageComponent]:
        """
        处理本地数据, 文本用str, 其他用路径
        """
        if data_type == "text":
            chain = [Comp.Plain(data)]

        elif data_type == "image":
            chain = [Comp.Image.fromFileSystem(data)]

        elif data_type == "video":
            chain = [Comp.Video.fromFileSystem(data)]

        elif data_type == "audio":
            chain = [Comp.Record.fromFileSystem(data)]

        return chain  # type: ignore

    def _get_nested_value(self, result: dict, target: str) -> Any:
        """
        从嵌套字典中根据指定路径获取值。

        :param result: 嵌套字典结构。
        :param target: 目标路径，如 "data.Msg" 或 "data[1].Msg" 或 "data[].Msg"。
        :return: 目标路径对应的值。如果路径无效或目标不存在，返回空字符串。
        """
        # 匹配点号（.）或方括号中的索引（包括空的[]），将目标路径拆分为键或索引。
        keys = [key for key in re.split(r"\.|(\[\d*\])", target) if key and key.strip()]

        value = result

        for key in keys:
            key = key.strip("[]")
            if isinstance(value, dict):
                value = value.get(key, "")
                if self.debug:
                    logger.debug(f"key: {key}, value: {value}")
            elif isinstance(value, list):
                if key == "":  # 如果是空的[]，随机选择一个元素
                    if value:
                        value = random.choice(value)
                        if self.debug:
                            logger.debug(f"key: {key}, value: {value}")
                    else:
                        return ""
                elif key.isdigit():  # 如果指定了索引
                    index = int(key)
                    if 0 <= index < len(value):
                        value = value[index]
                        if self.debug:
                            logger.debug(f"key: {key}, value: {value}")
                    else:
                        return ""
                else:
                    return ""
            else:
                return ""
        return value

    @staticmethod
    def _extract_url(text: str) -> str:
        """从字符串中提取第一个有效URL"""
        # 去掉转义字符
        text = text.replace("\\", "")

        # 定义URL匹配模式
        url_pattern = r"https?://[^\s\"']+"
        urls = re.findall(url_pattern, text)

        for url in urls:
            # 解码URL中的百分号编码
            url = unquote(url)

            # 去除URL头尾的多余双引号（如果存在）
            url = url.strip('"')

            # 解析URL
            parsed_url = urlparse(url)

            # 验证URL的有效性
            if parsed_url.scheme in {"http", "https"} and parsed_url.netloc:
                return url
        return ""

    async def _save_data(
        self, data: str | bytes, path_name: str, data_type: str
    ) -> str | Path | None:
        """将数据保存到本地"""

        # 如果数据是字符串，尝试从其中提取 URL 并下载数据
        if isinstance(data, str) and data_type != "text":
            if url := self._extract_url(data):
                result = await self._make_request(url)
                if isinstance(result, bytes):
                    data = result
                else:
                    logger.error(f"保存数据失败: {result}")
                    return None

        # 设定保存路径
        TYPE_DIR = TYPE_DIRS.get(data_type, Path("data/temp"))
        TYPE_DIR.mkdir(parents=True, exist_ok=True)

        # 保存文本
        if data_type == "text":
            json_path = TYPE_DIR / f"{path_name}.json"
            if not json_path.exists():
                json_path.write_text(
                    json.dumps([], ensure_ascii=False, indent=4), encoding="utf-8"
                )
                logger.info(f"{path_name}.json 文件不存在, 已创建一个空的 JSON 文件")
            try:
                json_data = json.loads(json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                json_data = []
                logger.error(
                    f"读取 {path_name}.json 文件失败, 已重置为一个空的 JSON 文件"
                )

            # 确保 json_data 是一个列表
            if not isinstance(json_data, list):
                json_data = []

            text = str(data)
            clean_text = text.replace("\\r", "\n")

            # 检查数据是否已存在，避免重复
            if data not in json_data:
                json_data.append(clean_text)
            # 写回更新后的 JSON 数据
            json_path.write_text(
                json.dumps(json_data, ensure_ascii=False, indent=4), encoding="utf-8"
            )

            return clean_text

        # 保存图片、视频、音频
        else:
            save_dir = TYPE_DIR / f"{path_name}"
            save_dir.mkdir(parents=True, exist_ok=True)
            extension = {
                "image": ".jpg",
                "audio": ".mp3",
                "video": ".mp4",
            }.get(data_type, ".jpg")
            index = len(list(save_dir.rglob("*")))
            save_path = save_dir / f"{path_name}_{index}_api{extension}"
            with open(save_path, "wb") as f:
                f.write(data)  # type: ignore
            return save_path


    async def _get_data(self, path_name: str, data_type: str) -> str | None:
        """
        从本地取出数据
        :param path_name: 数据的名称或路径
        :param data_type: 数据类型（如"text"、"image"等）
        :return: 数据内容或文件路径，如果失败返回None
        """
        # 数据保存路径
        TYPE_DIR = TYPE_DIRS.get(data_type, Path("data/temp"))

        # 随机取一条文本
        if data_type == "text":
            json_path = TYPE_DIR / f"{path_name}.json"
            if not json_path.exists():
                logger.error(f"文件不存在：{json_path}")
                return None

            try:
                json_data = json.loads(json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                logger.error(f"解析JSON文件失败：{json_path}，错误：{e}")
                return None

            if isinstance(json_data, list) and json_data:
                return random.choice(json_data)
            else:
                logger.error(f"JSON数据格式错误：{json_data}")
                return None

        # 随机取一张图片、视频、音频的路径
        else:
            save_dir = TYPE_DIR / f"{path_name}"
            if save_dir.exists():
                files = list(save_dir.iterdir())
                if files:
                    selected_file = random.choice(files)
                    return str(selected_file)
                else:
                    logger.error(f"目录为空：{save_dir}")
                    return None
            else:
                logger.error(f"目录不存在：{save_dir}")
                return None

    @staticmethod
    async def _get_extra(event: AstrMessageEvent, target_id: str):
        """从消息平台获取参数"""
        if event.get_platform_name() == "aiocqhttp":
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                AiocqhttpMessageEvent,
            )

            assert isinstance(event, AiocqhttpMessageEvent)
            client = event.bot
            user_info = await client.get_stranger_info(user_id=int(target_id))
            nickname = user_info.get("nickname")
            return nickname
        # TODO 适配更多消息平台

    @staticmethod
    def _dict_to_string(input_dict):
        """
        将字典转换为指定格式的字符串，支持嵌套字典。
        每一级缩进增加两个空格，直到解析到没有字典嵌套为止。

        参数:
            input_dict (dict): 输入的字典。

        返回:
            str: 格式化后的字符串。
        """
        def recursive_parse(d, level):
            result = ""
            indent = " " * (level * 2)  # 当前层级的缩进
            for key, value in d.items():
                if isinstance(value, dict):  # 如果值是字典，则递归处理
                    result += f"{indent}{key}:\n"
                    result += recursive_parse(value, level + 1)  # 增加缩进
                elif isinstance(value, list):
                    for item in value:
                        result += "\n\n"
                        result += recursive_parse(item, level)  # 增加缩进
                else:
                    result += f"{indent}{key}: {value}\n"
            return result.strip()

        return recursive_parse(input_dict, 0)

import asyncio
import json
import os
from pathlib import Path
import random
import re
from typing import Any, List, Optional, Union
import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.core.message.components import BaseMessageComponent
from astrbot.core.star.filter.event_message_type import EventMessageType


# 定义基础缓存路径
DATA_PATH = Path("./data/plugins_data/astrbot_plugin_apis")
DATA_PATH.mkdir(parents=True, exist_ok=True)

# 单独定义各个子路径
TEXT_DIR = DATA_PATH / "text"
IMAGE_DIR = DATA_PATH / "image"
VIDEO_DIR = DATA_PATH / "video"
AUDIO_DIR = DATA_PATH / "audio"
for path in [IMAGE_DIR, VIDEO_DIR, TEXT_DIR, AUDIO_DIR]:
    path.mkdir(parents=True, exist_ok=True)

TEXT_PATH = TEXT_DIR / "all_texts.json"
if not TEXT_PATH.exists():
    TEXT_PATH.write_text(json.dumps({}, ensure_ascii=False, indent=4), encoding="utf-8")

api_file = Path(__file__).parent / "api_data.json" # api_data.json 文件路径，更新插件时会被覆盖


class APIManager:
    def __init__(self, api_file=api_file):
        self.api_file = api_file
        self.apis = {}
        self.load_data()

    def load_data(self):
        """从JSON文件加载数据"""
        if os.path.exists(self.api_file):
            with open(self.api_file, "r", encoding="utf-8") as file:
                self.apis = json.load(file)
        else:
            self.save_data()

    def save_data(self):
        """将数据保存到JSON文件"""
        with open(self.api_file, "w", encoding="utf-8") as file:
            json.dump(self.apis, file, ensure_ascii=False, indent=4)

    def add_api(self, api_info: dict):
        """添加一个新的API"""
        self.apis[api_info["name"]] = api_info
        self.save_data()

    def remove_api(self, name):
        """移除一个API"""
        if name in self.apis:
            del self.apis[name]
            self.save_data()
        else:
            print(f"API '{name}' 不存在。")

    def get_api_info(self, name):
        """获取指定API的信息"""
        return self.apis.get(name, "API不存在")

    def get_apis_names(self):
        """获取所有API的名称"""
        return list(self.apis.keys())

    def check_duplicate_api(self, api_name: str):
        """检查是否有重复的API"""
        return api_name in self.apis

@register(
    "astrbot_plugin_apis",
    "Zhalslar",
    "API聚合插件，海量免费API动态添加，热门API：看看腿、看看腹肌...",
    "1.0.0",
    "https://github.com/Zhalslar/astrbot_plugin_apis",
)
class ArknightsPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.API = APIManager()
        self.apis_names = self.API.get_apis_names()
        self.debug = config.get("debug", False)  # 是否开启调试模式
        self.auto_save_data = config.get("auto_save_data", False)  # 是否保存数据
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
        # 匹配api
        msgs = event.get_message_str().split(" ")
        api_name = next((i for i in self.apis_names if i == msgs[0]), None)
        if not api_name:
            logger.debug("未找到API")
            return

        if api_name in self.disable_api:
            logger.debug("API已禁用")
            return

        # 获取api_data
        api_data: dict = self.API.apis.get(api_name, {})
        url: str = api_data.get("url", "")
        type: str = api_data.get("type", "image")
        params: dict = api_data.get("params", {})
        target: str = api_data.get("target", "")

        # 获取参数
        args = msgs[1:]

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

        # 发送请求
        result = await self._make_request(url=url, params=update_params)
        if self.debug:
            logger.debug(f"响应结果: \n{result}")

        # 处理响应
        chain = await self._process_result(
            result=result, api_name=api_name, data_type=type, target=target
        )

        # 发送消息
        yield event.chain_result(chain)  # type: ignore

    async def _process_result(
        self, api_name: str, result: Any, data_type: str, target: str = ""
    ) -> List[BaseMessageComponent]:
        """处理响应"""
        chain = [Comp.Plain("此API无响应")]

        if isinstance(result, dict) and target:
            result = self._get_nested_value(result, target)

        if data_type == "text":
            chain = [Comp.Plain(str(result))]

        elif data_type == "image":
            if isinstance(result, str):
                url = self._extract_url(result)
                if url:
                    chain = [Comp.Image.fromURL(url)]
                    if self.auto_save_data:
                        await self._save_data(result, api_name, data_type)
            elif isinstance(result, bytes):
                file_path = await self._save_data(result, api_name, data_type)
                chain = [Comp.Image.fromFileSystem(file_path)]
                if not self.auto_save_data:
                    os.remove(file_path)

        elif data_type == "video":
            if isinstance(result, str):
                url = self._extract_url(result)
                if url:
                    chain = [Comp.Video.fromURL(url)]
                    if self.auto_save_data:
                        await self._save_data(result, api_name, data_type)

            elif isinstance(result, bytes):
                file_path = await self._save_data(result, api_name, data_type)
                chain = [Comp.Video.fromFileSystem(file_path)]
                if not self.auto_save_data:
                    os.remove(file_path)

        elif data_type == "audio":
            if isinstance(result, str):
                url = self._extract_url(result)
                if url:
                    chain = [Comp.Record.fromURL(url)]
                    if self.auto_save_data:
                        await self._save_data(result, api_name, data_type)
            elif isinstance(result, bytes):
                file_path = await self._save_data(result, api_name, data_type)
                chain = [Comp.Record.fromFileSystem(file_path)]
                if not self.auto_save_data:
                    os.remove(file_path)

        return chain  # type: ignore

    @staticmethod
    def _extract_url(text: str) -> str:
        """从字符串中提取第一个有效URL"""
        url_pattern = r"https?://[^\s]+"
        urls = re.findall(url_pattern, text)
        if urls:
            return urls[0]
        else:
            return ""

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

    async def _save_data(self, data: str|bytes, path_name: str, data_type: str) -> str:
        """保存bytes数据到本地"""
        if isinstance(data, str):
            result = await self._make_request(data)
            if isinstance(result, bytes):
                data = result
            else:
                logger.error(f"保存数据失败: {result}")
                return ""

        # 保存目录
        save_dir =  {
            "text": TEXT_DIR,
            "image": IMAGE_DIR,
            "video": VIDEO_DIR,
            "audio": AUDIO_DIR,
        }.get(data_type, Path("data/temp"))
        save_dir.mkdir(parents=True, exist_ok=True)

        # 后缀名
        extension = {
            "image": ".jpg",
            "audio": ".mp3",
            "video": ".mp4",
        }.get(data_type, ".jpg")

        # 获取当前目录下同类型文件的数量
        pattern = f"*{extension}"
        index = len(list(save_dir.rglob(pattern)))

        # 构造保存路径
        save_path = save_dir / f"{path_name}_{index}_api{extension}"

        # 保存文件
        with open(save_path, "wb") as f:
            f.write(data)

        return str(save_path)





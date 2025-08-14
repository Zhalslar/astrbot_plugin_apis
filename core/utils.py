import random
import re
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from urllib.parse import unquote, urlparse

async def get_nickname(event: AstrMessageEvent, target_id: str):
    """从消息平台获取昵称"""
    if event.get_platform_name() == "aiocqhttp":
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )
        assert isinstance(event, AiocqhttpMessageEvent)
        client = event.bot
        user_info = await client.get_stranger_info(user_id=int(target_id))
        return user_info.get("nickname")
    # TODO 适配更多消息平台


def dict_to_string(input_dict):
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

def extract_url(text: str) -> str:
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


def get_nested_value(result: dict, target: str):
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
        elif isinstance(value, list):
            if key == "":  # 如果是空的[]，随机选择一个元素
                if value:
                    value = random.choice(value)
                else:
                    return ""
            elif key.isdigit():  # 如果指定了索引
                index = int(key)
                if 0 <= index < len(value):
                    value = value[index]
                else:
                    return ""
            else:
                return ""
        else:
            return ""
    return value

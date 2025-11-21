import random
import re
from urllib.parse import unquote, urlparse

from astrbot.core.platform.astr_message_event import AstrMessageEvent


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

def extract_urls(text: str, *, unique: bool = True) -> list[str]:
    """
    搜索式提取所有 http/https URL，不受前后干扰字符影响。
    """
    # 1. 搜索式正则：只要出现 http(s):// 就开始捕获，向后扩展到非法字符为止
    #    用捕获组把 URL 部分单独拿出来
    regex = re.compile(r'(https?://[^\s<>"{}|\\^`\[\]\')(),;]+\b)', re.IGNORECASE)
    candidates = regex.findall(text)

    # 2. 后处理
    valid, seen = [], set()
    for raw in candidates:
        raw = raw.strip("\"'")  # 去掉首尾引号
        raw = unquote(raw)  # 解码 %xx
        parsed = urlparse(raw)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            if unique and raw in seen:
                continue
            if unique:
                seen.add(raw)
            valid.append(raw)
    return valid

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


def parse_api_keys(api_keys: list[str]) -> dict[str, str]:
    """
    将 api_keys 列表解析为 {域名: api_key} 的映射字典
    格式: https://域名:api_key
    - 只切第二个冒号，防止 key 中包含冒号
    - 不会修改传入的 api_keys
    """
    result: dict[str, str] = {}
    for key_str in api_keys:
        if not key_str:
            continue
        key_str = key_str.strip().replace("：", ":")
        parts = key_str.split(":", 2)
        if len(parts) < 3:
            continue
        domain = parts[0] + ":" + parts[1]
        api_key = parts[2]  # 剩余部分作为 key
        result[domain] = api_key
    return  result

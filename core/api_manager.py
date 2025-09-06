
import ast
import copy
import json
import os
from typing import Any
from urllib.parse import urlparse
from astrbot.api import logger


class APIManager:
    """API管理器"""

    ALLOWED_TYPES = ["text", "image", "video", "audio"]  # 支持的 API 类型常量

    def __init__(self, system_api_file, user_api_file):
        self.system_api_file = system_api_file
        self.user_api_file = user_api_file
        self.system_apis = {}
        self.user_apis = {}
        self.load_data()
        self.default_api_type = "image"

    def load_data(self):
        """从 JSON 文件加载数据 (系统 + 用户)"""
        self.apis = {}
        self.system_apis = {}

        # 系统 API
        if os.path.exists(self.system_api_file):
            with open(self.system_api_file, "r", encoding="utf-8") as file:
                try:
                    self.system_apis.update(json.load(file))
                    self.apis.update(self.system_apis)
                    logger.info(f"已加载{len(self.system_apis.keys())}个系统 API")
                except json.JSONDecodeError:
                    logger.warning(f"{self.system_api_file} 格式错误，已跳过。")
        else:
            self._save_data(target="system")

        # 用户 API
        if os.path.exists(self.user_api_file):
            with open(self.user_api_file, "r", encoding="utf-8") as file:
                try:
                    user_data = json.load(file)              # 只 load 一次
                    self.user_apis.update(user_data)
                    self.apis.update(user_data)
                    logger.info(f"已加载{len(self.user_apis)}个用户 API")
                except json.JSONDecodeError:
                    logger.warning(f"{self.user_api_file} 格式错误，已跳过。")
        else:
            self._save_data(target = "user")

    def _save_data(self, target: str = "user"):
        """保存 API 数据"""
        if target == "system":
            with open(self.system_api_file, "w", encoding="utf-8") as file:
                json.dump(self.system_apis, file, ensure_ascii=False, indent=4)
        elif target == "user":
            with open(self.user_api_file, "w", encoding="utf-8") as file:
                json.dump(self.user_apis, file, ensure_ascii=False, indent=4)

    def add_api(self, api_info: dict):
        """添加一个新的API（只写入 user_file）"""
        name = api_info["keyword"][0]
        self.apis[name] = api_info
        self.user_apis[name] = api_info
        self._save_data()

    def remove_api(self, name: str):
        """移除一个API"""
        if name in self.user_apis:
            del self.user_apis[name]
            if name in self.apis:
                del self.apis[name]
            self._save_data("user")
            logger.info(f"已删除用户 API '{name}'。")

        elif name in self.system_apis:
            del self.system_apis[name]
            if name in self.apis:
                del self.apis[name]
            self._save_data("system")
            logger.info(f"已删除系统 API '{name}'。")

        else:
            logger.warning(f"API '{name}' 不存在。")

    @staticmethod
    def extract_base_url(full_url: str) -> str:
        """
        剥离 URL 中的站点部分，例如：
        输入: "https://api.pearktrue.cn/api/stablediffusion/"
        输出: "https://api.pearktrue.cn"
        """
        parsed = urlparse(full_url)
        return (
            f"{parsed.scheme}://{parsed.netloc}"
            if parsed.scheme and parsed.netloc
            else full_url
        )

    def get_apis_names(self):
        """获取所有API的名称"""
        names = []
        for api in self.apis.values():
            name_field = api.get("name", [])
            if isinstance(name_field, str):
                names.append(name_field)
            elif isinstance(name_field, list):
                names.extend(name_field)
        return names

    def normalize_api_data(self, name: str) -> dict:
        """标准化 API 配置，返回深拷贝，避免被外部修改"""
        raw_api = self.apis.get(name, {})
        url = raw_api.get("url", "")
        urls = [url] if isinstance(url, str) else url

        api_type = raw_api.get("type", "")
        if api_type not in self.ALLOWED_TYPES:
            api_type = self.default_api_type

        normalized = {
            "name": name,
            "urls": urls,
            "type": api_type,
            "params": raw_api.get("params", {}) or {},
            "target": raw_api.get("target", ""),
            "fuzzy": raw_api.get("fuzzy", False),
        }
        return copy.deepcopy(normalized)

    def match_api_by_name(self, msg: str) -> dict | None:
        """
        通过触发词匹配API，返回 (key, 处理过的api_data)。
        """
        for key, raw_api in self.apis.items():
            keywords = raw_api.get("keyword", [])
            if isinstance(keywords, str):
                keywords = [keywords]

            matched = False
            # 精准匹配
            if msg in keywords:
                matched = True
            # 模糊匹配
            elif raw_api.get("fuzzy", False) and any(k in msg for k in keywords):
                matched = True

            if matched:
                return self.normalize_api_data(key)

        return None

    def list_api(self):
        """
        根据API字典生成分类字符串,即api列表。
        """
        # 用 ALLOWED_TYPES 初始化分类字典
        api_types = {t: [] for t in self.ALLOWED_TYPES}

        # 遍历apis字典，按type分类
        for key, value in self.apis.items():
            api_type = value.get("type", "unknown")
            if api_type in api_types:
                api_types[api_type].append(key)

        # 生成最终字符串
        result = f"----共收录了{len(self.apis)}个API----\n\n"
        for api_type in api_types:
            if api_types[api_type]:
                result += f"【{api_type}】{len(api_types[api_type])}个：\n"
                for key in api_types[api_type]:
                    result += f"{key}、"
            result += "\n\n"

        return result.strip()

    def get_detail(self, api_name: str):
        """查看api的详细信息"""
        api_info = self.apis.get(api_name)
        if not api_info:
            return "API不存在"
        # 构造参数字符串
        params = api_info.get("params", {})
        params_list = [
            f"{key}={value}" if value is not None and value != "" else key
            for key, value in params.items()
        ]
        params_str = ",".join(params_list) if params_list else "无"

        return (
            f"api匹配词：{api_info.get('keyword') or '无'}\n"
            f"api地址：{api_info.get('url') or '无'}\n"
            f"api类型：{api_info.get('type') or '无'}\n"
            f"所需参数：{params_str}\n"
            f"解析路径：{api_info.get('target') or '无'}"
        )


    @staticmethod
    def from_detail_str(detail: str) -> dict:
        """
        将 get_detail 的字符串逆向解析为 API 配置字典
        """
        api_info = {}

        lines = detail.splitlines()
        for line in lines:
            if line.startswith("api匹配词："):
                kw = line.replace("api匹配词：", "").strip()
                if kw == "无":
                    api_info["keyword"] = []
                else:
                    # 如果 kw 是形如 "['xxx']" 的字符串，先转回 list
                    if (kw.startswith("[") and kw.endswith("]")):
                        try:
                            parsed = ast.literal_eval(kw)
                            if isinstance(parsed, list):
                                api_info["keyword"] = parsed
                            else:
                                api_info["keyword"] = [kw]
                        except Exception:
                            api_info["keyword"] = [kw]
                    else:
                        # 普通逗号分隔
                        api_info["keyword"] = [k.strip() for k in kw.split(",")]

            elif line.startswith("api地址："):
                url = line.replace("api地址：", "").strip()
                api_info["url"] = "" if url == "无" else url

            elif line.startswith("api类型："):
                api_type = line.replace("api类型：", "").strip()
                api_info["type"] = "" if api_type == "无" else api_type

            elif line.startswith("所需参数："):
                params_str = line.replace("所需参数：", "").strip()
                if params_str == "无":
                    api_info["params"] = {}
                else:
                    params = {}
                    for kv in params_str.split(","):
                        if "=" in kv:
                            k, v = kv.split("=", 1)
                            params[k.strip()] = v.strip()
                        else:
                            params[kv.strip()] = ""
                    api_info["params"] = params

            elif line.startswith("解析路径："):
                target = line.replace("解析路径：", "").strip()
                api_info["target"] = "" if target == "无" else target

        return api_info


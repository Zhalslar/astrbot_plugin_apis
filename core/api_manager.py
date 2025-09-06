from collections import defaultdict
import copy
import json
import os
from urllib.parse import urlparse
from astrbot.api import logger


class APIManager:
    """API管理器"""

    ALLOWED_TYPES = {"text", "image", "video", "audio"}  # 支持的 API 类型常量

    def __init__(self, api_file):
        self.api_file = api_file
        self.apis = {}
        self.load_data()
        self.default_api_type = "image"

    def load_data(self):
        """从JSON文件加载数据"""
        if os.path.exists(self.api_file):
            with open(self.api_file, "r", encoding="utf-8") as file:
                self.apis = json.load(file)
        else:
            self._save_data()

    def _save_data(self):
        """将数据保存到JSON文件"""
        with open(self.api_file, "w", encoding="utf-8") as file:
            json.dump(self.apis, file, ensure_ascii=False, indent=4)

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

    def add_api(self, api_info: dict):
        """添加一个新的API"""
        self.apis[api_info["name"][0]] = api_info
        self._save_data()

    def remove_api(self, name):
        """移除一个API"""
        if name in self.apis:
            del self.apis[name]
            self._save_data()
        else:
            logger.warning(f"API '{name}' 不存在。")

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

    def normalize_api_data(self, name: dict) -> dict:
        """标准化 API 配置，返回深拷贝，避免被外部修改"""
        raw_api = self.apis.get(name, {})
        url = raw_api.get("url", "")
        urls = [url] if isinstance(url, str) else url

        api_type = raw_api.get("type", "")
        if api_type not in self.ALLOWED_TYPES:
            api_type = self.default_api_type

        normalized = {
            "keyword": name,
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

    def get_urls_by_site(self) -> dict:
        """
        返回按站点分类的 URL 列表
        输出格式: {
            "https://api.pearktrue.cn": ["https://api.pearktrue.cn/api/stablediffusion/", ...],
            ...
        }
        """
        site_dict = defaultdict(list)
        for api in self.apis.values():
            urls = api.get("url", [])
            if isinstance(urls, str):
                urls = [urls]
            for u in urls:
                site = self.extract_base_url(u)
                site_dict[site].append(u)
        return dict(site_dict)

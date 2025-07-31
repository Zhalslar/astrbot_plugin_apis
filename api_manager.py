import json
import os
from astrbot.api import logger

class APIManager:
    def __init__(self, api_file):
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
        self.apis[api_info["name"][0]] = api_info
        self.save_data()

    def remove_api(self, name):
        """移除一个API"""
        if name in self.apis:
            del self.apis[name]
            self.save_data()
        else:
            logger.warning(f"API '{name}' 不存在。")

    def get_api_info(self, name):
        """获取指定API的信息"""
        return self.apis.get(name, "API不存在")

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

    def match_api_by_name(self, keyword: str) -> tuple[str, dict] | None:
        """
        通过触发词匹配API，返回对应的 key（原始键）和 API 数据。

        :param keyword: 输入的触发词
        :return: (key, api_dict) 或 None
        """
        for key, api in self.apis.items():
            names = api.get("name", [])
            if isinstance(names, str):
                names = [names]
            if keyword in names:
                return key, api
        return None

    def check_duplicate_api(self, api_name: str):
        """检查是否有重复的API"""
        return any(api_name in api.get("name", []) for api in self.apis.values())

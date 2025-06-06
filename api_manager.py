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
        self.apis[api_info["name"]] = api_info
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
        return list(self.apis.keys())

    def check_duplicate_api(self, api_name: str):
        """检查是否有重复的API"""
        return api_name in self.apis

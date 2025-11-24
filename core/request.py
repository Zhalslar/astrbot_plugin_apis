from bs4 import BeautifulSoup
import asyncio
from collections import defaultdict
from typing import Optional, Union
import aiohttp
from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from .api_manager import APIManager
from .utils import dict_to_string, extract_url, get_nested_value, parse_api_keys

class RequestManager:
    def __init__(self, config: AstrBotConfig, api_manager: APIManager) -> None:
        self.session = aiohttp.ClientSession()
        # api密钥字典
        self.api_key_dict = parse_api_keys(config.get("api_keys", []).copy())
        self.api_sites = list(self.api_key_dict.keys())
        self.api = api_manager

    async def request(self,
        urls: list[str], params: Optional[dict] = None, test_mode:bool=False
    ) -> Union[bytes, str, dict, None]:
        last_exc = None
        for u in urls:
            # 判断基础路径是否配置的key
            part = u.split("/")
            base_url = u[:len(part[0]) + len(part[2]) + 2]
            if self.api_key_dict.get(base_url):
                params["ckey"] = self.api_key_dict.get(base_url)

            try:
                async with self.session.get(u, params=params, timeout=30) as resp:
                    resp.raise_for_status()
                    if test_mode:
                        return
                    ct = resp.headers.get("Content-Type", "").lower()
                    if "application/json" in ct:
                        return await resp.json()
                    if "text/" in ct:
                        return (await resp.text()).strip()
                    return await resp.read()
            except Exception as e:
                last_exc = e
                logger.error(f"请求失败 {u}:{e}")
        if last_exc:
            raise last_exc

    async def get_data(
        self,
        urls: list[str],
        params: Optional[dict] = None,
        api_type: str = "",
        target: str = "",
    ) -> tuple[str | None, bytes | None]:
        """对外接口，获取数据"""

        data = await self.request(urls, params)

        # data为URL时，下载数据
        if isinstance(data, str) and api_type != "text":
            if url := extract_url(data):
                downloaded = await self.request(urls)
                if isinstance(downloaded, bytes):
                    data = downloaded
                else:
                    raise RuntimeError(f"下载数据失败: {url}")  # 抛异常给外部

        # data为字典时，解析字典
        if isinstance(data, dict) and target:
            nested_value = get_nested_value(data, target)
            if isinstance(nested_value, dict):
                data = dict_to_string(nested_value)
            else:
                data = nested_value

            # 如果字典里面的data是URL时，下载数据
            if isinstance(data, str) and api_type != "text":
                if url := extract_url(data):
                    downloaded = await self.request([data])
                    if isinstance(downloaded, bytes):
                        data = downloaded
                    else:
                        raise RuntimeError(f"下载数据失败: {url}")  # 抛异常给外部

        # data为HTML字符串时，解析HTML
        if isinstance(data, str) and data.strip().startswith("<!DOCTYPE html>"):
            soup = BeautifulSoup(data, "html.parser")
            # 提取HTML中的文本内容
            data = soup.get_text(strip=True)

        text = data if isinstance(data, str) else None
        byte = data if isinstance(data, bytes) else None

        return text, byte

    async def batch_test_apis(self) -> tuple[list[str], list[str]]:
        """
        将每个 URL 都作为独立测试项按站点分组；每轮从每个站点 pop 一个 URL 并发测试，直到所有 URL 测完。
        返回 (abled_api_list, disabled_api_list)
        """
        # 1) 展平每个 API 的所有 URL -> 按 site 分组
        site_to_entries = defaultdict(list)  # site -> list of entries
        for api_name, api_data in self.api.apis.items():
            url = api_data["url"]
            urls = [url] if isinstance(url, str) else url
            for u in urls:
                site = self.api.extract_base_url(u)
                site_to_entries[site].append(
                    {
                        "api_name": api_name,
                        "url": u,
                        "params": api_data.get("params", {}),
                    }
                )

        # 2) 记录每个 API 是否已成功（任一 URL 成功即为成功）
        api_succeeded = dict.fromkeys(self.api.apis.keys(), False)

        # 3) 按轮次从每个站点各取一个 URL 并发测试，直到所有站点的 entry 列表空
        while any(site_to_entries.values()):
            batch = []
            for site, entries in list(site_to_entries.items()):
                while entries:
                    batch.append(entries.pop(0))
                    break

            if not batch:
                break  # 没有需要测试的 entry 了

            # 并发测试这一轮的所有 URL
            tasks = [self.request([e["url"]], e["params"], True) for e in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理结果：任何非 Exception 的返回都视为成功
            for entry, res in zip(batch, results):
                if isinstance(res, Exception):
                    pass
                else:
                    api_succeeded[entry["api_name"]] = True

        # 4) 汇总
        abled = [k for k, v in api_succeeded.items() if v]
        disabled = [k for k, v in api_succeeded.items() if not v]
        return abled, disabled

    async def terminate(self):
        """关闭会话，断开连接"""
        await self.session.close()




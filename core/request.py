

from pathlib import Path
from typing import Optional, Union
import aiohttp
from astrbot.api import logger
from .utils import dict_to_string, extract_url, get_nested_value

class RequestManager:
    def __init__(self) -> None:
        self.session = aiohttp.ClientSession()

    async def _request(self,
        url: str | list[str], params: Optional[dict] = None
    ) -> Union[bytes, str, dict, None]:
        urls = [url] if isinstance(url, str) else url
        for u in urls:
            try:
                async with self.session.get(u, params=params, timeout=30) as resp:
                    resp.raise_for_status()
                    ct = resp.headers.get("Content-Type", "").lower()
                    if "application/json" in ct:
                        return await resp.json()
                    if "text/" in ct:
                        return (await resp.text()).strip()
                    return await resp.read()
            except Exception as e:
                logger.warning(f"请求失败: {u}, error: {e}")
        return None


    async def get_data(
        self, url: str | list[str], params: Optional[dict] = None, data_type: str = "", target: str = ""
    ) -> tuple[str | None, bytes | None]:
        """对外接口，获取数据"""

        data = await self._request(url, params)

        # data为URL时，下载数据
        if isinstance(data, str) and data_type != "text":
            if url := extract_url(data):
                downloaded = await self._request(url)
                if isinstance(downloaded, bytes):
                    data = downloaded
                else:
                    logger.error(f"下载数据失败: {url}")
                    return None, None

        # data为字典时，解析字典
        if isinstance(data, dict) and target:
            nested_value = get_nested_value(data, target)
            if isinstance(nested_value, dict):
                data = dict_to_string(nested_value)
            else:
                data = nested_value

        text = data if isinstance(data, str) else None
        byte = data if isinstance(data, bytes) else None

        return text, byte


    async def terminate(self):
        """关闭会话，断开连接"""
        if self.session:
            await self.session.close()

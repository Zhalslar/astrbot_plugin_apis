import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from ..entry import APIEntry, APIEntryManager, SiteEntryManager
from ..log import logger
from .request_result import RequestResult


class RemoteDataService:
    def __init__(
        self,
        api_mgr: APIEntryManager,
        site_mgr: SiteEntryManager,
    ) -> None:
        self.api_mgr = api_mgr
        self.site_mgr = site_mgr

        self.session: ClientSession | None = None

        self.default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
        }
        self.default_request_timeout = 60
        # Batch test pacing: sequential per site, parallel across sites.
        self.batch_site_interval_seconds = 0.2

    async def close(self):
        if self.session is not None and not self.session.closed:
            await self.session.close()
        self.session = None

    async def _ensure_session(self) -> ClientSession:
        if self.session is None or self.session.closed:
            self.session = ClientSession()
        return self.session

    def _build_request_args(self, entry: APIEntry):
        site = self.site_mgr.match_entry(entry.url)
        headers = site.get_headers() if site else self.default_headers.copy()
        keys = site.get_keys() if site else None
        params = dict(entry.params or {})
        params.update(dict(entry.updated_params or {}))
        timeout = site.timeout if site else self.default_request_timeout

        if keys:
            headers.update(keys)
            params.update(keys)

        return headers, params, timeout

    async def _request(
        self,
        url: str,
        *,
        headers: dict[str, Any],
        params: dict[str, Any],
        timeout: int = 60,
    ) -> RequestResult:
        result = RequestResult()

        try:
            session = await self._ensure_session()
            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=ClientTimeout(timeout),
            ) as resp:
                resp.raise_for_status()

                result.status = resp.status
                result.content_type = resp.headers.get("Content-Type", "").lower()
                result.final_url = str(resp.url)

                if "application/json" in result.content_type:
                    result.raw_text = await resp.text()
                    return result

                if "text/" in result.content_type:
                    result.raw_text = (await resp.text()).strip()
                    return result

                result.raw_content = await resp.read()
                return result

        except Exception as e:
            logger.error(f"Request failed {url}: {e}")
            result.error = str(e)
            return result

    async def get_data(self, entry: APIEntry) -> RequestResult:
        headers, params, timeout = self._build_request_args(entry)

        result = await self._request(
            entry.url,
            headers=headers,
            params=params,
            timeout=timeout,
        )

        if not result.ok:
            return result

        if entry.parse:
            result.parse_nested(entry.parse)

        for url in result.extract_urls():
            downloaded = await self._request(
                url,
                headers=headers,
                params=params,
                timeout=timeout,
            )
            if downloaded.is_binary:
                return downloaded

        result.extract_html_text()

        if not result.is_valid():
            result.error = result.error or "Invalid response"
            return result

        return result

    @staticmethod
    def _build_test_reason(result: RequestResult) -> str:
        if result.error:
            return result.error
        if not result.status:
            return "No HTTP status"
        if result.status < 200 or result.status >= 300:
            return f"HTTP {result.status}"
        if result.is_binary and not result.raw_content:
            return "Empty binary response"
        if result.is_text and not (result.raw_text or "").strip():
            return "Empty text response"
        if not result.is_valid():
            return "Business validation failed"
        return "ok"

    @staticmethod
    def _build_result_preview(result: RequestResult, limit: int = 220) -> str:
        if result.raw_text:
            text = result.raw_text.strip().replace("\r", " ").replace("\n", " ")
            if len(text) > limit:
                return f"{text[:limit]}..."
            return text
        if result.raw_content:
            return f"<binary {len(result.raw_content)} bytes>"
        return ""

    async def stream_test_apis(
        self,
        entries: list[APIEntry] | None = None,
        persist_valid_result: (
            Callable[[APIEntry, RequestResult], Awaitable[None]] | None
        ) = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Batch test APIs and yield progress events one by one.
        """
        entries = entries or self.api_mgr.list_entries()
        total = len(entries)
        if total == 0:
            yield {
                "event": "start",
                "total": 0,
                "completed": 0,
            }
            yield {
                "event": "done",
                "total": 0,
                "completed": 0,
                "valid": [],
                "invalid": [],
            }
            return

        site_to_entries: dict[str, list[APIEntry]] = defaultdict(list)
        for entry in entries:
            site_to_entries[entry.get_base_url()].append(entry)

        succeeded: set[str] = set()
        completed = 0

        yield {
            "event": "start",
            "total": total,
            "completed": completed,
        }

        queue: asyncio.Queue[
            tuple[APIEntry | None, RequestResult | Exception | None]
        ] = asyncio.Queue()

        async def site_worker(site_entries: list[APIEntry]) -> None:
            for index, entry in enumerate(site_entries):
                try:
                    result = await self.get_data(entry)
                    await queue.put((entry, result))
                except Exception as exc:
                    await queue.put((entry, exc))

                has_more = index < len(site_entries) - 1
                if has_more and self.batch_site_interval_seconds > 0:
                    await asyncio.sleep(self.batch_site_interval_seconds)

            await queue.put((None, None))

        site_workers = [
            asyncio.create_task(site_worker(list(site_entries)))
            for site_entries in site_to_entries.values()
            if site_entries
        ]

        completed_workers = 0
        total_workers = len(site_workers)
        persist_tasks: set[asyncio.Task[None]] = set()

        async def run_persist(entry: APIEntry, res: RequestResult) -> None:
            if persist_valid_result is None:
                return
            try:
                await persist_valid_result(entry, res)
            except Exception as exc:
                logger.warning(
                    "[api_aggregator] batch persist failed name=%s: %s",
                    entry.name,
                    exc,
                )

        while completed_workers < total_workers:
            entry, result = await queue.get()
            if entry is None:
                completed_workers += 1
                continue

            completed += 1

            if isinstance(result, Exception):
                yield {
                    "event": "progress",
                    "name": entry.name,
                    "url": entry.url,
                    "completed": completed,
                    "total": total,
                    "valid": False,
                    "status": None,
                    "content_type": "",
                    "final_url": "",
                    "reason": str(result),
                    "preview": "",
                }
                continue
            is_valid = result.is_valid()  # type: ignore
            if is_valid:
                succeeded.add(entry.name)
                if persist_valid_result is not None:
                    task = asyncio.create_task(run_persist(entry, result))  # type: ignore
                    persist_tasks.add(task)
                    task.add_done_callback(lambda t: persist_tasks.discard(t))

            yield {
                "event": "progress",
                "name": entry.name,
                "url": entry.url,
                "completed": completed,
                "total": total,
                "valid": is_valid,
                "status": result.status,  # type: ignore
                "content_type": result.content_type or "",  # type: ignore
                "final_url": result.final_url or "",  # type: ignore
                "reason": self._build_test_reason(result),  # type: ignore
                "preview": self._build_result_preview(result),  # type: ignore
            }

        if site_workers:
            await asyncio.gather(*site_workers, return_exceptions=True)

        success_names = list(succeeded)
        failed_names = [entry.name for entry in entries if entry.name not in succeeded]

        self.api_mgr.set_entries_valid(success_names, True)
        self.api_mgr.set_entries_valid(failed_names, False)

        yield {
            "event": "done",
            "total": total,
            "completed": completed,
            "valid": success_names,
            "invalid": failed_names,
            "success_count": len(success_names),
            "fail_count": len(failed_names),
        }

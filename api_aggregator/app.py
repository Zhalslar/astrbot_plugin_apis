from __future__ import annotations

import asyncio
from pathlib import Path

from ..config import PluginConfig
from .data_service import DataService, LocalDataService, RemoteDataService
from .database import SQLiteDatabase
from .entry import APIEntryManager, SiteEntryManager
from .log import logger, setup_default_logging
from .service import (
    ApiDeleteService,
    ApiTestService,
    PoolIOService,
    SiteSyncService,
)


class APICoreApp:
    """API aggregator runtime facade for framework integration.

    Typical usage:
    1. Create one `APICoreApp` instance per bot process.
    2. Call `await start()` on framework startup.
    3. Use `api_mgr.match_entries(...)` + `data_service.fetch(...)` in message handlers.
    4. Call `await stop()` on framework shutdown.
    """

    def __init__(self, config: PluginConfig):
        """Initialize runtime components"""

        self.cfg = config
        setup_default_logging()
        self.db = SQLiteDatabase(self.cfg.data_dir)
        self.local = LocalDataService(self.cfg.local_dir)
        self.api_mgr = APIEntryManager(self.db)
        self.site_mgr = SiteEntryManager(self.db)
        self.remote = RemoteDataService(self.api_mgr, self.site_mgr)
        self.data_service = DataService(self.remote, self.local)
        self.site_sync_service = SiteSyncService(self.api_mgr, self.site_mgr)
        self.api_delete_service = ApiDeleteService(self.api_mgr)
        self.api_test_service = ApiTestService(self.remote, self.local, self.api_mgr)
        self.pool_io_service = PoolIOService(
            self.cfg.pool_files_dir,
            self.db,
            self.api_mgr,
            self.site_mgr,
            resolve_site_name=self.site_sync_service.resolve_api_site_name,
            sync_sites=self.site_sync_service.sync_all_api_sites,
        )

        self._started = False

    async def start(self) -> None:
        """Start core services.

        Safe to call multiple times.
        Repeated calls after successful startup are ignored.
        """
        if self._started:
            logger.info("[app] start skipped: already running")
            return
        logger.info("[app] starting api-aggregator")
        logger.info("[app] data dir: %s", self.cfg.data_dir)
        self.db.reload_from_database()
        logger.info(
            "[app] database loaded: sites=%d, apis=%d",
            len(self.db.site_pool),
            len(self.db.api_pool),
        )
        await asyncio.gather(
            self.api_mgr.initialize(),
            self.site_mgr.initialize(),
        )
        logger.info("[app] api entries: %d", len(self.api_mgr.entries))
        logger.info("[app] site entries: %d", len(self.site_mgr.entries))
        self._started = True
        logger.info("[app] startup complete")

    async def stop(self) -> None:
        """Stop core services and release network resources.

        Safe to call multiple times. Repeated calls after shutdown are ignored.
        """
        if not self._started:
            logger.info("[app] stop skipped: not running")
            return
        logger.info("[app] shutting down")
        await self.remote.close()
        logger.info("[app] remote session closed")
        self._started = False
        logger.info("[app] shutdown complete")

    def _load_pool_from_file(
        self, pool_type: str, file_path: str | Path
    ) -> dict[str, object]:
        path = Path(file_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if path.suffix.lower() != ".json":
            raise ValueError("only .json files are supported")
        if not path.exists() or not path.is_file():
            raise ValueError(f"file not found: {path}")
        result = self.pool_io_service.import_pool_from_bytes(
            pool_type, path.read_bytes()
        )
        result["file_path"] = str(path)
        return result

    def load_site_pool_from_file(self, file_path: str | Path) -> dict[str, object]:
        """Load site pool data from a JSON file path."""
        return self._load_pool_from_file("site", file_path)

    def load_api_pool_from_file(self, file_path: str | Path) -> dict[str, object]:
        """Load api pool data from a JSON file path."""
        return self._load_pool_from_file("api", file_path)

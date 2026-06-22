from __future__ import annotations

from ..entry import APIEntryManager, SiteEntryManager


class SiteSyncService:
    """Handle site matching and api-site synchronization strategy."""

    def __init__(self, api_mgr: APIEntryManager, site_mgr: SiteEntryManager) -> None:
        self.api_mgr = api_mgr
        self.site_mgr = site_mgr

    def resolve_api_site_name(self, url: str) -> str:
        full_url = str(url or "").strip()
        if not full_url:
            return ""
        site = self.site_mgr.match_entry(full_url, only_enabled=False)
        return str(site.name) if site else ""

    def sync_all_api_sites(self) -> bool:
        return self.api_mgr.sync_site_fields(self.resolve_api_site_name)

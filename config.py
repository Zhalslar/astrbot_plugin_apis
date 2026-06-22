from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.context import Context
from astrbot.core.utils.astrbot_path import (
    get_astrbot_plugin_data_path,
    get_astrbot_plugin_path,
)

PLUGIN_NAME = "astrbot_plugin_apis"


class PluginConfig(BaseModel):
    need_prefix: bool = False
    save_data: bool = True
    use_local: bool = True
    admin_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")

    def __init__(self, config: AstrBotConfig, context: Context):
        super().__init__(**config)
        self.admin_ids = context.get_config().get("admins_id", [])
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.pool_files_dir.mkdir(parents=True, exist_ok=True)

    @property
    def plugin_dir(self) -> Path:
        return Path(get_astrbot_plugin_path()) / PLUGIN_NAME

    @property
    def data_dir(self) -> Path:
        return Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME

    @property
    def local_dir(self) -> Path:
        return self.data_dir / "local"

    @property
    def pool_files_dir(self) -> Path:
        return self.data_dir / "pool_files"

    @property
    def presets_dir(self) -> Path:
        return self.plugin_dir / "presets"

    @property
    def api_pool_file(self) -> Path:
        return self.presets_dir / "api_pool_default.json"

    @property
    def site_pool_file(self) -> Path:
        return self.presets_dir / "site_pool_default.json"

    @property
    def dashboard_dir(self) -> Path:
        return self.plugin_dir / "pages" / "dashboard"

    @property
    def dashboard_assets_dir(self) -> Path:
        return self.dashboard_dir / "assets"

    @property
    def logo_path(self) -> Path:
        return self.dashboard_assets_dir / "images" / "logo.png"

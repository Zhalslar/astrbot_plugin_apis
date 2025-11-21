import json
import random
from pathlib import Path


class LocalDataManagerError(Exception):
    """本地数据管理器异常"""

    pass


class LocalDataManager:
    """本地数据管理器（支持文本 / 二进制）"""

    _SUB_DIRS = ("text", "image", "video", "audio")

    def __init__(self, data_root: str | Path) -> None:
        self._root = Path(data_root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

        # 创建/缓存子目录
        self._type_dirs: dict[str, Path] = {}
        for sub in self._SUB_DIRS:
            p = self._root / sub
            p.mkdir(parents=True, exist_ok=True)
            self._type_dirs[sub] = p

    async def save_data(
        self,
        api_type: str,
        path_name: str,
        text: str | None = None,
        byte: bytes | None = None,
    ) -> tuple[str | None, Path | None]:
        """
        保存数据到本地
        :param api_type: 数据类型（如"text"、"image"等）
        :param path_name: 数据的名称或路径
        :return: 数据内容或文件路径，如果失败返回None
        """
        saved_text, saved_path = None, None

        type_dir = self._type_dirs.get(api_type, self._root / "temp")
        type_dir.mkdir(parents=True, exist_ok=True)

        # 文本
        if api_type == "text" and text:
            json_file = type_dir / f"{path_name}.json"
            if not json_file.exists():
                json_file.write_text("[]", encoding="utf-8")

            try:
                items = json.loads(json_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                items = []

            if not isinstance(items, list):
                items = []

            saved_text = str(text).replace("\\r", "\n")
            if saved_text not in items:
                items.append(saved_text)
            json_file.write_text(
                json.dumps(items, ensure_ascii=False, indent=4), encoding="utf-8"
            )
        # 图片、视频、音频
        elif byte:
            save_dir = type_dir / path_name
            save_dir.mkdir(parents=True, exist_ok=True)
            ext = {"image": ".jpg", "audio": ".mp3", "video": ".mp4"}.get(
                api_type, ".bin"
            )
            idx = len(list(save_dir.iterdir()))
            saved_path = save_dir / f"{path_name}_{idx}_api{ext}"
            saved_path.write_bytes(byte)  # type: ignore[arg-type]

        return saved_text, saved_path

    async def get_data(
        self, api_type: str, path_name: str
    ) -> tuple[str | None, Path | None]:
        """
        从本地随机读取一条数据
        :param path_name: 数据的名称或路径
        :param api_type: 数据类型（如"text"、"image"等）
        :return: 数据内容或文件路径，如果失败返回None
        """
        text, path = None, None

        type_dir = self._type_dirs.get(api_type, self._root / "temp")

        # 文本
        if api_type == "text":
            json_file = type_dir / f"{path_name}.json"
            if not json_file.exists():
                raise LocalDataManagerError(f"文本数据集不存在: {json_file}")

            try:
                items = json.loads(json_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise LocalDataManagerError(f"解析 JSON 失败: {json_file}, 错误: {e}")

            if not isinstance(items, list) or not items:
                raise LocalDataManagerError(f"文本数据集为空或格式错误: {json_file}")

            text = random.choice(items)
            return text, None

        # 图片、视频、音频
        else:
            folder = type_dir / path_name
            if not folder.exists():
                raise LocalDataManagerError(f"目录不存在: {folder}")

            files = list(folder.iterdir())
            if not files:
                raise LocalDataManagerError(f"目录为空: {folder}")

            path = random.choice(files)

            return None, path

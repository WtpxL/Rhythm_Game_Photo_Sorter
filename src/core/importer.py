"""图片导入扫描：从文件夹中找出支持的图片文件并统计。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# 常见图片格式（小写）。来源图片只读，不在此做任何修改。
SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
    ".gif",
    ".tif",
    ".tiff",
}


@dataclass(frozen=True)
class ImageFile:
    """一张待处理图片。"""

    path: Path
    size_bytes: int


@dataclass
class ImportResult:
    """一次文件夹扫描的结果与统计。"""

    images: list[ImageFile] = field(default_factory=list)
    scanned_files: int = 0
    skipped_unsupported: int = 0
    skipped_unreadable: int = 0

    @property
    def total_found(self) -> int:
        return len(self.images)


ProgressCallback = Callable[[int, int], None]


def is_supported_image(path: Path) -> bool:
    """判断文件扩展名是否属于受支持的图片格式。"""
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def scan_folder(
    folder: str | Path,
    recursive: bool = False,
    progress: ProgressCallback | None = None,
) -> ImportResult:
    """扫描文件夹，返回支持的图片列表与统计。"""
    root = Path(folder)
    if not root.is_dir():
        raise NotADirectoryError(f"不是有效文件夹：{folder}")

    entries = list(root.rglob("*")) if recursive else list(root.iterdir())
    result = ImportResult()
    total = len(entries)

    for index, entry in enumerate(entries, start=1):
        if progress is not None:
            progress(index, total)
        if not entry.is_file():
            continue
        result.scanned_files += 1
        if not is_supported_image(entry):
            result.skipped_unsupported += 1
            continue
        try:
            size_bytes = entry.stat().st_size
        except OSError:
            result.skipped_unreadable += 1
            continue
        result.images.append(ImageFile(path=entry, size_bytes=size_bytes))

    result.images.sort(key=lambda image: image.path.name.lower())
    return result

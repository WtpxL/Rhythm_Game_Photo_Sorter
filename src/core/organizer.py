"""整理：把已确认的图片移动到 sorted/游戏/歌名/。"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from src.core.paths import organized_root

_INVALID_CHARS = re.compile(r'[\\/:*?"<>|]')


def sanitize_component(name: str) -> str:
    """把目录/文件名中的非法字符替换为安全字符。"""
    cleaned = _INVALID_CHARS.sub("_", name).strip()
    return cleaned or "_"


def _unique_destination(directory: Path, filename: str) -> Path:
    """在目录内为同名文件生成不冲突的目标路径（追加 _1、_2）。"""
    destination = directory / filename
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    for index in range(1, 1000):
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"同名文件过多，无法生成唯一文件名：{destination}")


def unique_destination(directory: str | Path, filename: str) -> Path:
    """在目录内为同名文件生成不冲突的目标路径（追加 _1、_2）。公开封装。"""
    return _unique_destination(Path(directory), filename)


def _move_to(source: Path, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = _unique_destination(directory, source.name)
    shutil.move(str(source), str(destination))
    return destination


def organize_into(source: str | Path, game: str, title: str) -> Path:
    """移动到 sorted/<游戏>/<歌名>/<原文件名>，返回目标路径。"""
    source_path = Path(source)
    directory = organized_root() / sanitize_component(game) / sanitize_component(title)
    return _move_to(source_path, directory)

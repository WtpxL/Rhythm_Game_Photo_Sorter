"""生成外置曲库文件：从内置 library.db 导出各游戏到 config/SongLists/<file>.json。

曲库外置后，程序运行时优先读取 Program/SongLists/ 下的可编辑文件；本脚本用于：
- 开发期把曲库（含别名）导出到项目根 config/SongLists/；
- 打包前生成随包分发的默认 SongLists/。

用法：python scripts/export_song_lists.py [--force]
不加 --force 时，已存在的外置曲库文件不会被覆盖（保护人工修改）。
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.library import store


def main() -> None:
    force = "--force" in sys.argv
    created = store.export_all(force=force)
    print("导出目录：", store.song_lists_dir())
    for game in store.GAMES:
        path = store.song_file(game)
        count = len(store._read_songs_from_file(path)) if path.exists() else 0
        print(f"  {path.name}: {count} 首")
    if created:
        print("本次写入：", ", ".join(created))
    else:
        print("外置曲库已存在，未覆盖（如需强制重建请加 --force）。")


if __name__ == "__main__":
    main()

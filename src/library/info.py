"""曲库信息：读取外置曲库（SongLists/）的更新时间与各游戏统计（只读）。

供「曲库信息」界面展示：曲库目录、更新时间、各游戏曲目数与含别名曲目数。
联网刷新与曲库外置详见 docs/04 阶段 10。
"""

from __future__ import annotations

from datetime import datetime

from src.library import store

GAMES = store.GAMES


def format_time(iso: str | None) -> str:
    """把 ISO 时间转成本地可读文本；解析失败时原样返回。"""
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


def song_stats() -> dict:
    """返回曲库统计：目录、更新时间、总曲目数与各游戏曲目/别名数。"""
    return store.stats()

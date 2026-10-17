"""外置曲库：从程序同级的 config/SongLists/ 读取各游戏可编辑的歌名库。

每个游戏一个文件（config/SongLists/<file>.json，共三个：Arcaea.json / maimai.json / chunithm.json），
结构如下，人工可直接编辑歌名与别名：

{
  "game": "arcaea",
  "name": "Arcaea",
  "updated_at": "2026-10-15T16:43:00+00:00",
  "songs": [
    {"title": "歌名原文", "aliases": ["别名1", "别名2"]}
  ]
}

- 程序运行时优先从 config/SongLists/ 读取曲库；文件缺失或损坏时，回退到打包内置的 library.db（首次运行会用内置曲库
  自动生成一份 config/SongLists/ 供人工修改）。
- 图片内容只读；本模块只读/生成曲库文本文件，不触碰图片。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.core.paths import library_db, song_lists_dir

GAMES = ("arcaea", "maimai", "chunithm")
GAME_NAMES = {"arcaea": "Arcaea", "maimai": "舞萌", "chunithm": "中二节奏"}
FILENAMES = {"arcaea": "Arcaea.json", "maimai": "maimai.json", "chunithm": "chunithm.json"}

# 曲库文件解析缓存：{路径: (mtime, [(title, [aliases])])}。
_cache: dict[str, tuple[float, list[tuple[str, list[str]]]]] = {}


def song_file(game: str) -> Path:
    """某游戏外置曲库文件的路径。"""
    return song_lists_dir() / FILENAMES[game]


def _parse_aliases(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item).strip()]
    return []


def _read_songs_from_file(path: Path) -> list[tuple[str, list[str]]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    songs: list[tuple[str, list[str]]] = []
    for item in data.get("songs", []):
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        aliases = [str(a).strip() for a in item.get("aliases", []) if str(a).strip()]
        songs.append((title, aliases))
    return songs


def _read_songs_from_db(game: str) -> list[tuple[str, list[str]]]:
    conn = sqlite3.connect(library_db())
    try:
        rows = conn.execute(
            "SELECT title, title_aliases FROM songs WHERE game=?", (game,)
        ).fetchall()
    finally:
        conn.close()
    return [(title, _parse_aliases(raw)) for title, raw in rows]


def load_songs(game: str) -> list[tuple[str, list[str]]]:
    """返回某游戏曲库 [(歌名, [别名])]。

    优先读 SongLists/<file>.json；文件不存在或无法解析时回退打包内置的 library.db。
    """
    path = song_file(game)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None

    if mtime is not None:
        cached = _cache.get(str(path))
        if cached is not None and cached[0] == mtime:
            return cached[1]
        try:
            songs = _read_songs_from_file(path)
        except (OSError, ValueError, KeyError):
            songs = None
        if songs is not None:
            _cache[str(path)] = (mtime, songs)
            return songs

    try:
        return _read_songs_from_db(game)
    except sqlite3.Error:
        return []


def _db_updated_at(game: str) -> str | None:
    try:
        conn = sqlite3.connect(library_db())
        try:
            row = conn.execute(
                "SELECT MAX(updated_at) FROM songs WHERE game=?", (game,)
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def build_payload(game: str) -> dict:
    """从打包内置曲库构造某游戏的外置曲库数据（不含写文件）。"""
    songs = _read_songs_from_db(game)
    return {
        "game": game,
        "name": GAME_NAMES.get(game, game),
        "updated_at": _db_updated_at(game) or datetime.now(timezone.utc).isoformat(),
        "songs": [{"title": title, "aliases": aliases} for title, aliases in songs],
    }


def export_game(game: str, force: bool = False) -> bool:
    """用内置曲库生成某游戏的外置曲库文件；已存在且 force=False 时跳过。"""
    path = song_file(game)
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_payload(game)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _cache.pop(str(path), None)
    return True


def export_all(force: bool = False) -> list[str]:
    """生成全部游戏的外置曲库文件，返回实际新建的文件名列表。"""
    return [FILENAMES[g] for g in GAMES if export_game(g, force=force)]


def ensure_song_lists() -> list[str]:
    """首次运行时若 SongLists/ 缺失，用内置曲库生成各游戏文件。返回新建的文件名列表。"""
    return export_all()


def stats() -> dict:
    """曲库统计（供「曲库信息」展示）：目录、总曲目数、更新时间与各游戏统计。"""
    directory = song_lists_dir()
    per_game: dict[str, dict] = {}
    total = 0
    latest: str | None = None
    for game in GAMES:
        songs = load_songs(game)
        with_alias = sum(1 for _title, aliases in songs if aliases)
        per_game[game] = {"total": len(songs), "with_alias": with_alias, "file": FILENAMES[game]}
        total += len(songs)
        path = song_file(game)
        try:
            updated = json.loads(path.read_text(encoding="utf-8")).get("updated_at")
        except (OSError, ValueError, AttributeError):
            updated = None
        if not updated:
            updated = _db_updated_at(game)
        if updated and (latest is None or updated > latest):
            latest = updated
    return {
        "dir": str(directory),
        "total": total,
        "updated_at": latest,
        "games": per_game,
    }

"""把抓取到的曲目标题与难度词表写入本地 SQLite 曲库。"""

import json
import os
import sqlite3
from datetime import datetime, timezone

# 过滤抓取时混入的非歌名标记（难度名/分类标记）。
# 注意：L9 是真实曲名，不能列入黑名单（曾误过滤，见 devlog 2026-10-16）。
BLOCKLIST = {
    "DX", "GO", "BASIC", "ADVANCED", "EXPERT", "MASTER", "Re:MASTER",
    "ULTIMA", "BSC", "ADV", "EXP", "MAS", "MST", "ReM", "PST", "PRS", "FTR", "BYD",
}

DIFFICULTIES = {
    "arcaea": [
        {"name": "PAST", "aliases": ["PST"]},
        {"name": "PRESENT", "aliases": ["PRS"]},
        {"name": "FUTURE", "aliases": ["FTR"]},
        {"name": "BEYOND", "aliases": ["BYD"]},
        {"name": "ETERNAL", "aliases": ["ETR"]},
        {"name": "INSCRIBED", "aliases": ["INS"]},
    ],
    "maimai": [
        {"name": "BASIC", "aliases": []},
        {"name": "ADVANCED", "aliases": []},
        {"name": "EXPERT", "aliases": []},
        {"name": "MASTER", "aliases": []},
        {"name": "Re:MASTER", "aliases": ["ReM", "RE:MASTER"]},
    ],
    "chunithm": [
        {"name": "BASIC", "aliases": ["BSC"]},
        {"name": "ADVANCED", "aliases": ["ADV"]},
        {"name": "EXPERT", "aliases": ["EXP"]},
        {"name": "MASTER", "aliases": ["MAS", "MST"]},
        {"name": "ULTIMA", "aliases": []},
        {"name": "WORLD'S END", "aliases": ["世界末日"]},
    ],
}


def load_titles(game: str) -> list[str]:
    with open("data/%s_titles.json" % game, encoding="utf-8") as fh:
        raw = json.load(fh)
    return [t.strip() for t in raw if t.strip() and t.strip() not in BLOCKLIST]


def main() -> None:
    os.makedirs("data", exist_ok=True)
    db_path = "data/library.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS songs ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "game TEXT NOT NULL,"
        "title TEXT NOT NULL,"
        "title_aliases TEXT NOT NULL DEFAULT '',"
        "updated_at TEXT NOT NULL,"
        "UNIQUE(game, title))"
    )
    now = datetime.now(timezone.utc).isoformat()
    for game in ["arcaea", "maimai", "chunithm"]:
        titles = load_titles(game)
        for title in titles:
            conn.execute(
                "INSERT OR IGNORE INTO songs(game, title, updated_at) VALUES(?, ?, ?)",
                (game, title, now),
            )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM songs WHERE game=?", (game,)).fetchone()[0]
        print(game, "inserted:", count)

    # 写入各游戏别名（data/<game>_aliases.json，格式同 arcaea_aliases.json）
    for game in ["arcaea", "maimai", "chunithm"]:
        alias_path = "data/%s_aliases.json" % game
        if not os.path.exists(alias_path):
            continue
        with open(alias_path, encoding="utf-8") as fh:
            alias_map = json.load(fh)
        applied = 0
        for title, info in alias_map.items():
            aliases = info.get("aliases", [])
            if not aliases:
                continue
            applied += conn.execute(
                "UPDATE songs SET title_aliases=? WHERE game=? AND title=?",
                (json.dumps(aliases, ensure_ascii=False), game, title),
            ).rowcount
        conn.commit()
        print("%s aliases applied:" % game, applied)
    conn.close()

    with open("data/difficulties.json", "w", encoding="utf-8") as fh:
        json.dump(DIFFICULTIES, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("wrote data/difficulties.json")


if __name__ == "__main__":
    main()

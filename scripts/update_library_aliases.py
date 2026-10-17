"""把抓取到的别名写入本地曲库 songs 表的 title_aliases 字段。

读取 data/<game>_aliases.json（arcaea / maimai / chunithm），格式同 arcaea_aliases.json。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "library.db"


def ensure_column(conn: sqlite3.Connection) -> None:
    columns = [row[1] for row in conn.execute("PRAGMA table_info(songs)").fetchall()]
    if "title_aliases" not in columns:
        conn.execute("ALTER TABLE songs ADD COLUMN title_aliases TEXT NOT NULL DEFAULT ''")
        conn.commit()


def main() -> None:
    conn = sqlite3.connect(DB)
    ensure_column(conn)

    for game in ["arcaea", "maimai", "chunithm"]:
        alias_path = BASE / "data" / ("%s_aliases.json" % game)
        if not alias_path.exists():
            continue
        with open(alias_path, encoding="utf-8") as fh:
            alias_map = json.load(fh)

        updated = 0
        for title, info in alias_map.items():
            aliases = info.get("aliases", [])
            if not aliases:
                continue
            cursor = conn.execute(
                "UPDATE songs SET title_aliases=? WHERE game=? AND title=?",
                (json.dumps(aliases, ensure_ascii=False), game, title),
            )
            updated += cursor.rowcount

        conn.commit()
        total = conn.execute(
            "SELECT COUNT(*) FROM songs WHERE game=? AND title_aliases != ''", (game,)
        ).fetchone()[0]
        print("%s: updated %d, with_aliases %d" % (game, updated, total))
    conn.close()


if __name__ == "__main__":
    main()

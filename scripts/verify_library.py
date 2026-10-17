"""抽查本地曲库中的几条数据。"""

import sqlite3


def main() -> None:
    conn = sqlite3.connect("data/library.db")
    checks = [
        ("maimai", "%グリーンライツ%"),
        ("arcaea", "Tutorial"),
        ("chunithm", "%シンメトリー%"),
        ("maimai", "%Bubble%"),
    ]
    for game, pat in checks:
        rows = conn.execute(
            "SELECT title FROM songs WHERE game=? AND title LIKE ? LIMIT 3", (game, pat)
        ).fetchall()
        print(game, pat, "->", [r[0] for r in rows])
    conn.close()


if __name__ == "__main__":
    main()

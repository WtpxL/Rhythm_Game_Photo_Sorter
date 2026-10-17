"""用玩家成绩导出 CSV 校验本地曲库覆盖率（仅作参照，来源不完整）。"""

from __future__ import annotations

import csv
import json
import sqlite3
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SCORES = {
    "maimai": BASE / "国服舞萌中二成绩" / "maimai-scores.csv",
    "chunithm": BASE / "国服舞萌中二成绩" / "chunithm-scores (2).csv",
}


def normalize(title: str) -> str:
    """NFKC 归一化后去空白、小写，用于吸收全半角/大小写差异。"""
    return "".join(unicodedata.normalize("NFKC", title).casefold().split())


def load_library_titles(game: str) -> dict[str, set[str]]:
    """返回曲库可匹配名集合：包含 title 与其 title_aliases（如中文译名/异写）。"""
    conn = sqlite3.connect(BASE / "data" / "library.db")
    rows = conn.execute("SELECT title, title_aliases FROM songs WHERE game=?", (game,)).fetchall()
    conn.close()
    exact: set[str] = set()
    for title, raw_aliases in rows:
        exact.add(title)
        try:
            for alias in json.loads(raw_aliases or "[]"):
                if isinstance(alias, str) and alias:
                    exact.add(alias)
        except (ValueError, TypeError):
            pass
    normalized = {normalize(t): t for t in exact}
    return {"exact": exact, "normalized": normalized}


def load_score_songs(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return [row["song_name"].strip() for row in reader if row.get("song_name", "").strip()]


def main() -> None:
    report: dict[str, dict] = {}
    for game, path in SCORES.items():
        songs = load_score_songs(path)
        unique = sorted(set(songs))
        library = load_library_titles(game)

        matched = [t for t in unique if t in library["exact"]]
        matched_normalized_only = [
            t for t in unique if t not in library["exact"] and normalize(t) in library["normalized"]
        ]
        missing = [
            t for t in unique
            if t not in library["exact"] and normalize(t) not in library["normalized"]
        ]

        report[game] = {
            "csv_total_rows": len(songs),
            "unique_songs": len(unique),
            "matched_exact": len(matched),
            "matched_after_normalize": len(matched_normalized_only),
            "missing": missing,
        }

        print(f"[{game}] 记录 {len(songs)} 条，去重歌名 {len(unique)} 个")
        print(f"  精确命中：{len(matched)}")
        print(f"  归一化后命中：{len(matched_normalized_only)}（如全半角差异）")
        print(f"  缺失：{len(missing)}")
        for title in matched_normalized_only[:30]:
            print(f"    ~ {title}")

    out = BASE / "data" / "validation_missing.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写出完整缺失清单：{out}")


if __name__ == "__main__":
    main()

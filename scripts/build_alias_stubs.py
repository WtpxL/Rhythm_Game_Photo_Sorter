"""为舞萌 / 中二节奏生成别名源文件 data/<game>_aliases.json 的骨架。

与 Arcaea 的别名机制保持一致：把该游戏全部曲目登记为
``{"main": <歌名>, "aliases": []}``，后续再逐步为需要中文译名 / 异写的曲目补充别名。
已存在的非空别名（例如舞萌「Bad Apple!! feat nomico」的标点别名）会被保留，不覆盖。

生成的别名文件由 scripts/build_library.py 或 scripts/update_library_aliases.py
写入本地曲库 songs.title_aliases 字段。Arcaea 已有抓取生成的别名文件，不在此处理。
"""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
GAMES = ["maimai", "chunithm"]


def build(game: str) -> None:
    titles_path = BASE / "data" / f"{game}_titles.json"
    alias_path = BASE / "data" / f"{game}_aliases.json"

    titles = json.loads(titles_path.read_text(encoding="utf-8"))
    existing: dict[str, dict] = {}
    if alias_path.exists():
        existing = json.loads(alias_path.read_text(encoding="utf-8"))

    result: dict[str, dict] = {}
    for raw in titles:
        title = raw.strip()
        if not title:
            continue
        prev = existing.get(title)
        aliases = list(prev.get("aliases", [])) if prev else []
        result[title] = {"main": title, "aliases": aliases}

    # 保留已有但不在 titles 中的条目，避免丢失历史别名。
    for title, info in existing.items():
        result.setdefault(title, info)

    alias_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with_alias = sum(1 for info in result.values() if info.get("aliases"))
    print(f"{game}: {len(result)} 条曲目，非空别名 {with_alias} 条 -> {alias_path.name}")


def main() -> None:
    for game in GAMES:
        build(game)


if __name__ == "__main__":
    main()

"""把打包版运行时 config/SongLists/ 里人工补充的别名同步回工程。

打包后的程序会在 exe 同级生成 config/SongLists/*.json（可人工编辑）。用户在打包版里
补充别名后，用本脚本把这些别名合并回工程：

1. data/<game>_aliases.json —— 工程内的别名「源」（结构 {title: {main, aliases}}）；
2. config/SongLists/<game>.json —— 工程的运行时曲库（结构 {"songs":[{title, aliases}]}）。

合并为「并集」，只新增不删除，绝不覆盖工程里已有的别名。

用法::

    python scripts/import_aliases_from_runtime.py                 # 预览差异（dry-run）
    python scripts/import_aliases_from_runtime.py --apply         # 写入工程并同步
    python scripts/import_aliases_from_runtime.py --source DIR    # 指定运行时目录
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = BASE / "dist" / "音游成绩图分类工具" / "config" / "SongLists"

FILENAMES = {"arcaea": "Arcaea.json", "maimai": "maimai.json", "chunithm": "chunithm.json"}


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _runtime_aliases(data: dict) -> dict[str, list[str]]:
    """解析运行时 SongLists 结构 {"songs":[{title, aliases}]}。"""
    result: dict[str, list[str]] = {}
    for item in data.get("songs", []):
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        result[title] = [str(a).strip() for a in item.get("aliases", []) if str(a).strip()]
    return result


def _source_aliases(data: dict) -> dict[str, list[str]]:
    """解析工程源文件结构 {title: {main, aliases}}。"""
    result: dict[str, list[str]] = {}
    for title, info in data.items():
        if not isinstance(info, dict):
            continue
        result[title] = [str(a).strip() for a in info.get("aliases", []) if str(a).strip()]
    return result


def collect(source_dir: Path) -> dict[str, dict[str, list[str]]]:
    """返回 {game: {title: [相对源文件新增的别名]}}。"""
    added: dict[str, dict[str, list[str]]] = {}
    for game, filename in FILENAMES.items():
        runtime = _runtime_aliases(_load(source_dir / filename))
        repo = _source_aliases(_load(BASE / "data" / ("%s_aliases.json" % game)))
        game_added: dict[str, list[str]] = {}
        for title, aliases in runtime.items():
            existing = set(repo.get(title, []))
            new = [a for a in aliases if a not in existing]
            if new:
                game_added[title] = new
        added[game] = game_added
    return added


def apply(source_dir: Path) -> None:
    for game, filename in FILENAMES.items():
        runtime = _runtime_aliases(_load(source_dir / filename))
        path = BASE / "data" / ("%s_aliases.json" % game)
        by_title = _load(path)
        for title, aliases in runtime.items():
            entry = by_title.get(title)
            if not isinstance(entry, dict):
                entry = {"main": title, "aliases": []}
                by_title[title] = entry
            merged = entry.setdefault("aliases", [])
            for a in aliases:
                if a and a not in merged:
                    merged.append(a)
        path.write_text(json.dumps(by_title, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        count = sum(1 for v in by_title.values() if isinstance(v, dict) and v.get("aliases"))
        print("%s: 源文件已更新，%d 首有别名" % (game, count))


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="同步打包版运行时别名回工程")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE),
                        help="打包版运行时 config/SongLists 目录")
    parser.add_argument("--apply", action="store_true", help="写入工程并同步 SongLists")
    args = parser.parse_args()

    source_dir = Path(args.source)
    print("运行时目录：%s" % source_dir)
    if not source_dir.is_dir():
        print("目录不存在，退出。")
        return

    added = collect(source_dir)
    any_change = False
    for game, entries in added.items():
        if not entries:
            print("%s: 无新增别名" % game)
            continue
        any_change = True
        print("%s: 发现 %d 首有新增别名" % (game, len(entries)))
        for title, aliases in entries.items():
            print("    %s -> %s" % (title, aliases))

    if not any_change:
        print("没有需要同步的别名。")
        return
    if not args.apply:
        print("\n（dry-run）加 --apply 才会写入工程。")
        return

    print("\n写入工程 data/<game>_aliases.json ...")
    apply(source_dir)
    print("\n同步到 config/SongLists/ ...")
    sys.path.insert(0, str(BASE / "scripts"))
    from build_all_aliases import sync_to_songlists  # noqa: E402
    sync_to_songlists()
    print("\n完成。")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""构建并同步三大音游的曲名别名（含中文/日文译名）。

- Arcaea：抓取 wiki.arcaea.cn 全量曲目信息框，提取「第二曲名 / 中文名 / 别名 / 第二名称」
  作为别名。抓取结果与已有别名文件「并集」合并，绝不覆盖人工补充的别名。
- 舞萌 / 中二：保留已有别名，为全部曲目补齐骨架条目（别名可空），便于人工/学习机制补充。

构建完成后把别名差异同步到程序同级的 config/SongLists/<game>.json（运行时实际读取的曲库）。

用法::

    python scripts/build_all_aliases.py                # 抓取 + 构建 + 同步
    python scripts/build_all_aliases.py --no-scrape    # 用已缓存的别名文件 + 构建 + 同步
    python scripts/build_all_aliases.py --sync-only    # 仅同步到 SongLists
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
ARCAEA_API = "https://wiki.arcaea.cn/api.php"
ARCAEA_FIELDS = ["第二曲名", "中文名", "别名", "第二名称"]

SONGLIST_FILES = {
    "arcaea": "Arcaea.json",
    "maimai": "maimai.json",
    "chunithm": "chunithm.json",
}


def _clean_wiki_value(raw: str) -> str:
    """清洗 MediaWiki 模板/链接标记，返回纯文本别名。"""
    val = raw.strip()
    val = re.sub(r"\{\{Lang\|[^}]+\|([^}]+)\}\}", r"\1", val)
    val = re.sub(r"\{\{[^}]*\}\}", "", val)
    val = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", r"\1", val)
    return val.strip()


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


def _merge_aliases(existing: dict, scraped: dict) -> dict:
    """把抓取到的别名并入已有别名（并集，保序：先抓取后人工）。"""
    result: dict[str, dict] = {}
    for title, info in scraped.items():
        prev = existing.get(title, {}).get("aliases", [])
        merged: list[str] = []
        for alias in list(info.get("aliases", [])) + list(prev):
            if alias and alias not in merged:
                merged.append(alias)
        result[title] = {"main": info.get("main", title), "aliases": merged}
    # 保留已有但本次未抓到的曲目（避免丢失历史别名）。
    for title, info in existing.items():
        result.setdefault(title, info)
    return result


def scrape_arcaea() -> dict:
    """抓取 Arcaea wiki 全量曲目的第二曲名/中文名等别名。"""
    from playwright.sync_api import sync_playwright

    with open(BASE / "data" / "arcaea_titles.json", encoding="utf-8") as f:
        titles = json.load(f)

    print("Arcaea: 抓取 %d 个曲目页面的第二曲名 ..." % len(titles))
    result: dict[str, dict] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA)
        page = context.new_page()
        page.goto("https://wiki.arcaea.cn/index.php/首页",
                  wait_until="domcontentloaded", timeout=60000)
        for _ in range(60):
            time.sleep(1)
            if "not a bot" not in page.title().lower():
                break

        for i in range(0, len(titles), 50):
            batch = titles[i:i + 50]
            params = {
                "action": "query", "prop": "revisions", "rvprop": "content",
                "rvslots": "main", "titles": "|".join(batch), "format": "json",
            }
            data = context.request.get(
                ARCAEA_API + "?" + urllib.parse.urlencode(params)
            ).json()

            for _pid, pageobj in data.get("query", {}).get("pages", {}).items():
                title = pageobj.get("title", "")
                revs = pageobj.get("revisions", [])
                aliases: list[str] = []
                if revs:
                    content = revs[0]["slots"]["main"]["*"]
                    for field in ARCAEA_FIELDS:
                        for m in re.finditer(
                            r"\|\s*" + field + r"\s*=\s*(.+)", content
                        ):
                            val = _clean_wiki_value(m.group(1))
                            if val and val != title and val not in aliases:
                                aliases.append(val)
                result[title] = {"main": title, "aliases": aliases}

            done = min(i + 50, len(titles))
            with_cnt = sum(1 for v in result.values() if v["aliases"])
            print("  %d/%d  (%d 首有别名)" % (done, len(titles), with_cnt))
            time.sleep(0.2)

        browser.close()
    return result


def build_arcaea(no_scrape: bool) -> dict:
    alias_path = BASE / "data" / "arcaea_aliases.json"
    existing = _load_json(alias_path)
    if no_scrape:
        print("Arcaea: --no-scrape，使用已缓存别名文件（%d 条）" % len(existing))
        return existing
    scraped = scrape_arcaea()
    result = _merge_aliases(existing, scraped)
    alias_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with_cnt = sum(1 for v in result.values() if v.get("aliases"))
    print("  -> 合并后 %d/%d 首有别名（保留人工别名）" % (with_cnt, len(result)))
    return result


def build_stub_aliases(game: str) -> dict:
    """为舞萌/中二补齐全部曲目的别名骨架，保留已有别名。"""
    titles_path = BASE / "data" / ("%s_titles.json" % game)
    alias_path = BASE / "data" / ("%s_aliases.json" % game)

    with open(titles_path, encoding="utf-8") as f:
        titles = json.load(f)
    existing = _load_json(alias_path)

    result: dict[str, dict] = {}
    for raw in titles:
        title = raw.strip()
        if not title:
            continue
        prev = existing.get(title)
        result[title] = {
            "main": title,
            "aliases": list(prev.get("aliases", [])) if prev else [],
        }
    for title, info in existing.items():
        result.setdefault(title, info)

    alias_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with_cnt = sum(1 for v in result.values() if v.get("aliases"))
    print("%s: %d 条曲目，%d 条有别名" % (game, len(result), with_cnt))
    return result


def sync_to_songlists() -> None:
    songlists_dir = BASE / "config" / "SongLists"
    for game, filename in SONGLIST_FILES.items():
        alias_path = BASE / "data" / ("%s_aliases.json" % game)
        alias_data = _load_json(alias_path)
        songlist_path = songlists_dir / filename
        if not alias_data or not songlist_path.exists():
            print("%s: 跳过（缺别名源或 SongLists 文件）" % game)
            continue

        sl = json.loads(songlist_path.read_text(encoding="utf-8"))
        index = {k: v.get("aliases", []) for k, v in alias_data.items()}
        updated = 0
        for song in sl.get("songs", []):
            aliases = index.get(song["title"], [])
            if song.get("aliases", []) != aliases:
                song["aliases"] = aliases
                updated += 1
        if updated:
            sl["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            songlist_path.write_text(
                json.dumps(sl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        with_cnt = sum(1 for s in sl.get("songs", []) if s.get("aliases"))
        print("%s: %d 首曲目，%d 首有别名（更新 %d）"
              % (game, len(sl.get("songs", [])), with_cnt, updated))


def main() -> None:
    parser = argparse.ArgumentParser(description="构建并同步曲名别名")
    parser.add_argument("--no-scrape", action="store_true",
                        help="跳过联网抓取，使用已缓存的别名文件")
    parser.add_argument("--sync-only", action="store_true",
                        help="仅把已有别名文件同步到 config/SongLists/")
    args = parser.parse_args()

    if not args.sync_only:
        print("=" * 60)
        print("步骤 1：Arcaea")
        print("=" * 60)
        build_arcaea(no_scrape=args.no_scrape)
        print()
        print("=" * 60)
        print("步骤 2：舞萌 / 中二")
        print("=" * 60)
        for game in ["maimai", "chunithm"]:
            build_stub_aliases(game)

    print()
    print("=" * 60)
    print("步骤 3：同步到 config/SongLists/")
    print("=" * 60)
    sync_to_songlists()
    print()
    print("完成。")


if __name__ == "__main__":
    main()

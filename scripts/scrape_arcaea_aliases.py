"""抓取 Arcaea 各曲目的别名（第二曲名/中文名/别名），生成 title -> aliases 映射。"""

from __future__ import annotations

import json
import re
import time
import urllib.parse

from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
API = "https://wiki.arcaea.cn/api.php"

INFOBOX_RE = re.compile(r"\{\{曲目信息(.*?)\n\}\}", re.DOTALL)
LANG_RE = re.compile(r"\{\{lang\|[a-zA-Z-]*\|([^}]+)\}\}", re.IGNORECASE)
LINK_RE = re.compile(r"\[\[([^\]|]*\|)?([^\]]+)\]\]")


def clean(value: str) -> str:
    value = value.strip()
    match = LANG_RE.search(value)
    if match:
        value = match.group(1)
    value = re.sub(r"\{\{[^}]*\}\}", "", value)
    value = LINK_RE.sub(lambda m: m.group(2), value)
    value = value.replace("[[", "").replace("]]", "")
    return value.strip().strip("|")


def api_get(context, params):
    resp = context.request.get(API + "?" + urllib.parse.urlencode(params))
    return json.loads(resp.text())


def parse_page(title: str, content: str) -> tuple[str, list[str]]:
    fields: dict[str, list[str]] = {}
    block = INFOBOX_RE.search(content)
    if block:
        for line in block.group(1).splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            body = line[1:].strip()
            if "=" not in body:
                continue
            name, _, value = body.partition("=")
            value = clean(value)
            if value:
                fields.setdefault(name.strip(), []).append(value)

    main = (fields.get("曲名") or [title])[0]
    aliases: set[str] = set()
    for name in ("第二曲名", "中文名", "别名", "第二名称"):
        for value in fields.get(name, []):
            if value and value != main:
                aliases.add(value)
    return main, sorted(aliases)


def main() -> None:
    with open("data/arcaea_titles.json", encoding="utf-8") as fh:
        titles = json.load(fh)

    result: dict[str, dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA)
        page = context.new_page()
        page.goto("https://wiki.arcaea.cn/index.php/首页", wait_until="domcontentloaded", timeout=60000)
        for _ in range(60):
            time.sleep(1)
            if "not a bot" not in page.title().lower():
                break

        for i in range(0, len(titles), 50):
            batch = titles[i : i + 50]
            data = api_get(
                context,
                {
                    "action": "query",
                    "prop": "revisions",
                    "rvprop": "content",
                    "rvslots": "main",
                    "titles": "|".join(batch),
                    "format": "json",
                },
            )
            pages = data.get("query", {}).get("pages", {})
            for _pid, pageobj in pages.items():
                title = pageobj.get("title")
                revisions = pageobj.get("revisions", [])
                if not revisions:
                    result[title] = {"main": title, "aliases": []}
                    continue
                content = revisions[0]["slots"]["main"]["*"]
                main, aliases = parse_page(title, content)
                result[title] = {"main": main, "aliases": aliases}
            print("fetched", min(i + 50, len(titles)), "/", len(titles))
            time.sleep(0.2)

        browser.close()

    with open("data/arcaea_aliases.json", "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    with_alias = {k: v["aliases"] for k, v in result.items() if v["aliases"]}
    print("songs with aliases:", len(with_alias), "/", len(result))
    for k in sorted(with_alias)[:20]:
        print(k, "->", with_alias[k])


if __name__ == "__main__":
    main()

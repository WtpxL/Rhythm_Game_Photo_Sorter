"""抓取 Arcaea 全部曲目标题（通过「曲包曲目」子分类枚举）。"""

import json
import os
import time
import urllib.parse

from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
API = "https://wiki.arcaea.cn/api.php"


def api_get(context, params):
    resp = context.request.get(API + "?" + urllib.parse.urlencode(params))
    return json.loads(resp.text())


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA)
        page = context.new_page()
        page.goto("https://wiki.arcaea.cn/index.php/首页", wait_until="domcontentloaded", timeout=60000)
        for _ in range(45):
            time.sleep(1)
            if "not a bot" not in page.title().lower():
                break

        data = api_get(
            context,
            {"action": "query", "list": "categorymembers",
             "cmtitle": "Category:曲包曲目", "cmtype": "subcat",
             "cmlimit": "max", "format": "json"},
        )
        subcats = [m["title"] for m in data.get("query", {}).get("categorymembers", [])]
        print("pack subcategories:", len(subcats))

        titles = set()
        for cat in subcats + ["Category:非正式游戏杂曲目"]:
            d = api_get(
                context,
                {"action": "query", "list": "categorymembers",
                 "cmtitle": cat, "cmnamespace": 0,
                 "cmlimit": "max", "format": "json"},
            )
            for m in d.get("query", {}).get("categorymembers", []):
                titles.add(m["title"])
            time.sleep(0.1)

        ordered = sorted(titles)
        os.makedirs("data", exist_ok=True)
        with open("data/arcaea_titles.json", "w", encoding="utf-8") as fh:
            json.dump(ordered, fh, ensure_ascii=False, indent=2)
        print("total titles:", len(ordered))
        print("sample:", ordered[:15])

        browser.close()


if __name__ == "__main__":
    main()

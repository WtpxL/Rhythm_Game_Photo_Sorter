"""探查 Arcaea wiki 页面结构，确认曲名别名字段。"""

from __future__ import annotations

import json
import sys
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
    titles = sys.argv[1:] or ["April showers", "Lilly"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA)
        page = context.new_page()
        page.goto("https://wiki.arcaea.cn/index.php/首页", wait_until="domcontentloaded", timeout=60000)
        for _ in range(60):
            time.sleep(1)
            if "not a bot" not in page.title().lower():
                break

        for title in titles:
            data = api_get(
                context,
                {
                    "action": "query",
                    "prop": "revisions",
                    "rvprop": "content",
                    "rvslots": "main",
                    "titles": title,
                    "format": "json",
                },
            )
            pages = data.get("query", {}).get("pages", {})
            for _pid, pageobj in pages.items():
                revisions = pageobj.get("revisions", [])
                content = revisions[0]["slots"]["main"]["*"] if revisions else "(missing)"
                print("=" * 20, pageobj.get("title"))
                print(content[:3000])
            time.sleep(0.2)

        browser.close()


if __name__ == "__main__":
    main()

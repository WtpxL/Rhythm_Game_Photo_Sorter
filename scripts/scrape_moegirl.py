"""抓取萌娘百科舞萌/中二的完整曲目列表（专门的曲目列表子页面）。"""

import json
import os
import re
import time
import urllib.parse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

TITLE_KEYS = {
    "maimai": {"标题", "曲名", "曲目名"},
    "chunithm": {"标题", "曲名", "曲目名", "乐曲", "楽曲"},
}
SKIP = {"", "—", "/", "?", "展开", "曲名", "乐曲"}


def clean_title(text: str) -> str:
    t = text.strip()
    t = re.sub(r"\s*\[(DX|ST|STD|MURASAKi|MiLK|UNiVERSE|Splash|BUDDiES)\]\s*$", "", t)
    return t.strip()


def extract_titles(html: str, keys) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    titles: set[str] = set()
    for table in soup.find_all("table"):
        header_col = None
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if any(c.name == "th" for c in cells):
                for idx, c in enumerate(cells):
                    if c.name == "th" and c.get_text(" ", strip=True) in keys:
                        header_col = idx
                        break
            if header_col is not None:
                break
        if header_col is None:
            continue
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) <= header_col:
                continue
            cell = cells[header_col]
            if cell.name != "td":
                continue
            text = clean_title(cell.get_text(" ", strip=True))
            if text and text not in SKIP:
                titles.add(text)
    return sorted(titles)


def main() -> None:
    os.makedirs("data", exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA)
        page = context.new_page()

        for game, page_title in [("maimai", "Maimai系列/曲目列表"), ("chunithm", "CHUNITHM/曲目列表")]:
            page.goto(
                "https://zh.moegirl.org.cn/index.php?title=" + urllib.parse.quote(page_title),
                wait_until="domcontentloaded",
                timeout=120000,
            )
            page.wait_for_timeout(5000)
            titles = extract_titles(page.content(), TITLE_KEYS[game])
            with open("data/%s_titles.json" % game, "w", encoding="utf-8") as fh:
                json.dump(titles, fh, ensure_ascii=False, indent=2)
            print(game, "titles:", len(titles))
            print("   sample:", titles[:15])

        browser.close()


if __name__ == "__main__":
    main()

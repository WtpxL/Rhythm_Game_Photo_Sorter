"""临时探测脚本：验证萌娘百科三款游戏页面能否通过 HTML 或 extracts 接口取到数据。"""

import json
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TOKENS = ["BASIC", "ADVANCED", "EXPERT", "MASTER", "ULTIMA", "Re:MASTER", "PST", "PRS", "FTR", "BYD"]


def fetch_html(title: str) -> str:
    url = "https://zh.moegirl.org.cn/index.php?title=" + urllib.parse.quote(title)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8", "replace")


def fetch_extracts(title: str) -> str:
    url = (
        "https://zh.moegirl.org.cn/api.php?action=query&prop=extracts"
        "&explaintext=1&redirects=1&titles="
        + urllib.parse.quote(title)
        + "&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    if "query" not in data:
        raise RuntimeError(str(data)[:200])
    page = next(iter(data["query"]["pages"].values()))
    return page.get("extract", "")


def main() -> None:
    for title in ["Maimai系列", "CHUNITHM", "Arcaea"]:
        try:
            html = fetch_html(title)
            print(title, "html_len=", len(html), "html_tokens=", {t: html.count(t) for t in ["MASTER", "EXPERT"]})
        except Exception as exc:  # noqa: BLE001
            print(title, "html ERROR:", exc)
        try:
            ext = fetch_extracts(title)
            print(title, "extract_len=", len(ext), "extract_tokens=", {t: ext.count(t) for t in TOKENS})
        except Exception as exc:  # noqa: BLE001
            print(title, "extract ERROR:", exc)


if __name__ == "__main__":
    main()

"""分析抓取的曲目标题，找出明显的污染条目。"""

import json
import re

DIFF_TOKENS = {
    "BASIC", "ADVANCED", "EXPERT", "MASTER", "Re:MASTER", "ULTIMA",
    "BSC", "BAS", "ADV", "EXP", "MAS", "MST", "ReM", "PST", "PRS", "FTR", "BYD",
    "—", "/", "?", "",
}


def suspicious(title: str) -> bool:
    if title in DIFF_TOKENS:
        return True
    if re.fullmatch(r"\d+[+]?", title):
        return True
    if re.fullmatch(r"[A-Za-z0-9+./()\- ]{0,2}", title) and len(title) <= 2:
        return True
    return False


def main() -> None:
    for game in ["maimai", "chunithm", "arcaea"]:
        with open("data/%s_titles.json" % game, encoding="utf-8") as fh:
            titles = json.load(fh)
        bad = [t for t in titles if suspicious(t)]
        print(game, "total:", len(titles), "| suspicious:", len(bad), "| sample:", bad[:40])


if __name__ == "__main__":
    main()

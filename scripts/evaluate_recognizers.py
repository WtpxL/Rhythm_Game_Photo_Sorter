"""在舞萌/中二样例图上评估识别器，输出难度命中率与状态分布。"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.recognizers.pipeline import recognize_image

SUITES = {
    "maimai": "舞萌成绩图",
    "chunithm": "中二节奏成绩图",
}


def main() -> None:
    for game, folder in SUITES.items():
        paths = sorted((BASE / folder).glob("*.jpg"))
        difficulty_found = 0
        game_correct = 0
        status_counter: Counter[str] = Counter()
        lines: list[str] = []
        for path in paths:
            predicted_game, result = recognize_image(path)
            if predicted_game == game:
                game_correct += 1
            if result and result.difficulty:
                difficulty_found += 1
            status = result.status if result else "unknown"
            status_counter[status] += 1
            title = ""
            if result:
                title = result.title or (
                    result.title_candidates[0][0] if result.title_candidates else "—"
                )
            difficulty = result.difficulty if result else None
            lines.append(
                f"{path.name[:24]:<24} game={predicted_game:<9} "
                f"status={status:<9} diff={difficulty or '—':<10} title={title}"
            )

        total = len(paths)
        print(f"\n===== {game}：{total} 张 =====")
        print(f"游戏分类正确：{game_correct}/{total}")
        print(f"难度命中：{difficulty_found}/{total}")
        print(f"状态分布：{dict(status_counter)}")
        for line in lines:
            print(line)


if __name__ == "__main__":
    main()

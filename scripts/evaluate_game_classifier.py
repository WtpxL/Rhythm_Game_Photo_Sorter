"""在现有样例图上评估游戏分类器。"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.recognizers.game_classifier import classify

GROUND_TRUTH = {
    "舞萌成绩图": "maimai",
    "中二节奏成绩图": "chunithm",
    "Arcaea成绩图": "arcaea",
}


def main() -> None:
    total = 0
    correct = 0
    unknown = 0
    confusion: Counter[tuple[str, str]] = Counter()
    errors: list[tuple[str, str, str]] = []

    for folder, truth in GROUND_TRUTH.items():
        for path in sorted((BASE / folder).iterdir()):
            predicted = classify(path)
            total += 1
            confusion[(truth, predicted)] += 1
            if predicted == "unknown":
                unknown += 1
            elif predicted == truth:
                correct += 1
            else:
                errors.append((truth, predicted, path.name))

    decided = total - unknown
    print(f"总图数：{total}，正确：{correct}，存疑：{unknown}")
    print(f"有把握的图准确率：{correct}/{decided} = {correct / decided:.2%}")
    print(f"总体正确率（存疑不计入正确）：{correct / total:.2%}")
    for truth in ["arcaea", "maimai", "chunithm"]:
        row = {pred: confusion[(truth, pred)] for pred in ["arcaea", "maimai", "chunithm", "unknown"]}
        print(f"  {truth}: {row}")
    if errors:
        print("误分类：")
        for truth, predicted, name in errors:
            print(f"  {name} 真实={truth} 预测={predicted}")


if __name__ == "__main__":
    main()

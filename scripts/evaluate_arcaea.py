"""在 Arcaea 样例图上评估识别器：游戏分类、难度命中、歌名状态与失败类型。"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.recognizers.pipeline import recognize_image

FOLDER = "Arcaea成绩图"


def classify_failure(game: str, status: str, difficulty, observed: str) -> str:
    """给失败样本归类，便于统计失败类型。"""
    reasons: list[str] = []
    if game != "arcaea":
        reasons.append("游戏分类错误")
    if not difficulty:
        reasons.append("难度缺失")
    if status == "deferred":
        reasons.append("歌名未匹配（无有效文本）" if not observed.strip() else "歌名未匹配（候选过低）")
    elif status == "pending":
        reasons.append("歌名候选待人工确认")
    return "+".join(reasons) or "其他"


def main() -> None:
    folder = BASE / FOLDER
    paths = sorted(
        p for p in folder.iterdir()
        if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    )
    total = len(paths)
    game_ok = 0
    difficulty_ok = 0
    status_counter: Counter[str] = Counter()
    failure_types: Counter[str] = Counter()
    fails: list[tuple] = []

    for index, path in enumerate(paths, start=1):
        game, result = recognize_image(path)
        if game == "arcaea":
            game_ok += 1
        difficulty = result.difficulty if result else None
        if difficulty:
            difficulty_ok += 1
        status = result.status if result else "unknown"
        status_counter[status] += 1
        title = result.title if result else None
        observed = getattr(result, "observed_title_text", "") if result else ""
        candidates = result.title_candidates if result else []
        print(
            f"[{index}/{total}] {path.name} game={game} status={status} "
            f"diff={difficulty or '-'} title={title or '-'}",
            flush=True,
        )
        if game != "arcaea" or not difficulty or status != "confirmed":
            reason = classify_failure(game, status, difficulty, observed)
            failure_types[reason] += 1
            fails.append((path.name, game, status, difficulty, title, observed, candidates[:3]))

    print("\n===== Arcaea 全量评估 =====")
    print(f"图片总数：{total}")
    print(f"游戏分类正确（arcaea）：{game_ok}/{total}")
    print(f"难度命中：{difficulty_ok}/{total}")
    print(f"歌名自动确认（confirmed）：{status_counter['confirmed']}/{total}")
    print(f"状态分布：{dict(status_counter)}")
    print(f"未完全自动通过（需人工/失败）：{len(fails)}")
    for reason, count in failure_types.most_common():
        print(f"  失败类型 {reason}：{count}")
    print("--- 明细 ---")
    for name, game, status, difficulty, title, observed, candidates in fails:
        print(
            f"  - {name} game={game} status={status} diff={difficulty or '-'} "
            f"title={title or '-'}\n      observed={observed!r} cands={candidates}"
        )


if __name__ == "__main__":
    main()

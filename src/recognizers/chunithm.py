"""中二节奏结算图识别：屏幕定位后，按固定 ROI 提取难度与歌名。"""

from __future__ import annotations

from pathlib import Path

from src.recognizers.common import (
    RecognitionResult,
    collect_lines,
    find_difficulty,
    get_engine,
    load_and_prepare,
    rank_title_candidates_with_japanese,
)

GAME = "chunithm"

# 歌名与难度都位于画面右侧；难度在上、歌名在下，因此歌名行用难度 y 做下限过滤。
DIFFICULTY_ROI = (0.66, 0.02, 0.98, 0.20)
TITLE_ROI = (0.66, 0.05, 0.98, 0.24)


def extract(view, ocr_result) -> RecognitionResult:
    """从屏幕裁剪图与 OCR 结果中提取难度与歌名。"""
    height, width = view.shape[:2]
    difficulty_lines = collect_lines(ocr_result, DIFFICULTY_ROI, width, height)
    found = find_difficulty(difficulty_lines, GAME)
    difficulty = found[0] if found else None

    title_lines = collect_lines(ocr_result, TITLE_ROI, width, height)
    min_cy = None
    if found is not None:
        min_cy = found[1]
        title_lines = [line for line in title_lines if line[1] > min_cy]

    title, status, candidates, observed = rank_title_candidates_with_japanese(
        GAME, view, title_lines, TITLE_ROI, width, height, min_cy=min_cy
    )
    return RecognitionResult(
        title=title,
        difficulty=difficulty,
        status=status,
        title_candidates=candidates,
        observed_title_text=observed,
    )


def recognize(image_path: str | Path) -> RecognitionResult:
    """识别一张中二节奏结算图，返回歌名候选、难度与状态。"""
    view = load_and_prepare(image_path)
    if view is None:
        return RecognitionResult(title=None, difficulty=None, status="deferred")
    ocr_result, _ = get_engine()(view)
    return extract(view, ocr_result)

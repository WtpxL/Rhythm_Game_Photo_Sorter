"""Arcaea 结算图识别：难度固定区域直读，歌名区域文本与曲库模糊匹配。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtGui import QImage

from src.library.matcher import search_titles
from src.recognizers.common import ROI, get_engine

# 用相对宽高的比例表示 ROI，兼容微信压缩后的等比缩放。Arcaea 有两种截图布局：
#  - 平板截图：约 2360x1640（宽高比 ~1.44），歌名在上、曲师名紧贴其下一行；
#  - 手机横屏截图：约 2400x1080（宽高比 ~2.22），整体重排、各元素上移，需另取一套比例。
# 歌名 ROI 的下沿刻意卡在歌名行与曲师名之间，避免把曲师名（Cosmograph / cubesato 等）读进歌名。
TABLET_DIFFICULTY_ROI = (0.06, 0.31, 0.16, 0.37)
TABLET_TITLE_ROI = (0.28, 0.16, 0.72, 0.245)
PHONE_DIFFICULTY_ROI = (0.10, 0.26, 0.32, 0.35)
PHONE_TITLE_ROI = (0.28, 0.10, 0.72, 0.18)
# 宽高比达到此值即按手机横屏布局处理（平板 ~1.44，手机 ~2.22）。
PHONE_ASPECT_MIN = 1.8


def _select_rois(width: int, height: int) -> tuple[ROI, ROI]:
    """按截图宽高比返回 (难度 ROI, 歌名 ROI)；手机横屏用另一套比例。"""
    aspect = width / height if height else 0.0
    if aspect >= PHONE_ASPECT_MIN:
        return PHONE_DIFFICULTY_ROI, PHONE_TITLE_ROI
    return TABLET_DIFFICULTY_ROI, TABLET_TITLE_ROI


DIFFICULTIES = ("PAST", "PRESENT", "FUTURE", "BEYOND", "ETERNAL", "INSCRIBED")

@dataclass
class ArcaeaResult:
    title: str | None
    difficulty: str | None
    status: str
    title_candidates: list[tuple[str, float]] = field(default_factory=list)
    observed_title_text: str = ""


def _center(box: list) -> tuple[float, float]:
    xs = [point[0] for point in box]
    ys = [point[1] for point in box]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def recognize(image_path: str | Path) -> ArcaeaResult:
    """识别一张 Arcaea 结算图，返回歌名候选、难度与状态。"""
    image_path = str(image_path)
    ocr_result, _ = get_engine()(image_path)

    image = QImage(image_path)
    width, height = image.width(), image.height()
    difficulty_roi, title_roi = _select_rois(width, height)

    title_lines: list[tuple[str, float]] = []
    difficulty_texts: list[tuple[str, float]] = []
    for box, text, score in (ocr_result or []):
        cx, cy = _center(box)
        nx, ny = cx / width, cy / height
        if difficulty_roi[0] <= nx <= difficulty_roi[2] and difficulty_roi[1] <= ny <= difficulty_roi[3]:
            difficulty_texts.append((text, cy))
        if title_roi[0] <= nx <= title_roi[2] and title_roi[1] <= ny <= title_roi[3]:
            title_lines.append((text, cy))

    title_lines.sort(key=lambda item: item[1])
    difficulty_texts.sort(key=lambda item: item[1])

    difficulty = None
    for text, _cy in difficulty_texts:
        upper = text.strip().upper()
        for name in DIFFICULTIES:
            if upper == name or upper.startswith(name[:3]):
                difficulty = name
                break
        if difficulty:
            break

    observed = " ".join(text for text, _ in title_lines)
    queries = [observed] + [text for text, _ in title_lines]
    candidates: dict[str, float] = {}
    for query in queries:
        for title, score in search_titles("arcaea", query, limit=8):
            candidates[title] = max(candidates.get(title, 0.0), score)
    ranked = sorted(candidates.items(), key=lambda item: item[1], reverse=True)

    best_title = None
    status = "deferred"
    if ranked and ranked[0][1] >= 0.75:
        best_title, _ = ranked[0]
        status = "confirmed"
    elif ranked and ranked[0][1] >= 0.45:
        status = "pending"

    return ArcaeaResult(
        title=best_title,
        difficulty=difficulty,
        status=status,
        title_candidates=ranked[:5],
        observed_title_text=observed,
    )

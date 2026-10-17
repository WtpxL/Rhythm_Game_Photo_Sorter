"""游戏识别：Arcaea 靠格式/分辨率；街机游戏优先按 OCR 文字布局区分。

舞萌与中二的颜色会随版本、灯光、压缩而变化，因此主流程用结算画面的专属标签
判断；文字特征缺失时才回退到色彩启发式（classify）。
中二：JUSTICE/ATTACK/绝对正义/攻击。
舞萌：ACHIEVEMENT（日服）/「达成」（国服），以及舞萌独有的音符类型
（TOUCH触摸、BREAK绝赞）与 DX 计分（DX分数/DX评分）。国服舞萌竖屏图常同时拍到
「上屏」，其内容会干扰色彩启发式，故需靠上述文字标签兜底。
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PySide6.QtGui import QImage

ARCAEA_RESOLUTION = (2360, 1640)
# Arcaea iPad 截图宽高比容差（允许小幅缩放/裁剪）。
_ARCAEA_ASPECT = ARCAEA_RESOLUTION[0] / ARCAEA_RESOLUTION[1]  # ~1.439
_ARCAEA_ASPECT_TOLERANCE = 0.05
# 移动端/平板截图最大宽边；超过此值视为高分辨率实拍照片，不走 Arcaea 路径。
_ARCAEA_MAX_DIM = 3000
# 手机横屏 Arcaea 截图（如 2400x1080，约 20:9）宽高比区间；明显宽于平板布局。
_ARCAEA_PHONE_ASPECT_MIN = 1.7
_ARCAEA_PHONE_ASPECT_MAX = 2.6


# 舞萌/中二色彩阈值（4096x3072 实拍照片实测）。
_MAIMAI_R_MAX = 109.0
_MAIMAI_BLUE_MIN = 0.08
_MAIMAI_WHITE_MAX = 0.03
_MAIMAI_BLUE_HIGH = 0.23

# 用结算画面里的专属标签判断街机游戏：颜色会随版本/灯光变化，文字布局更稳定。
# 中二：JUSTICE/ATTACK 判定与中文名。舞萌：ACHIEVEMENT/达成率，
# 以及舞萌独有的音符类型（TOUCH/BREAK）与 DX 计分，覆盖含「上屏」的竖屏国服图。
_CHUNITHM_KEYS = ("justice", "attack", "绝对正义", "正义", "攻击")
_MAIMAI_KEYS = (
    "achievement",
    "达成",
    "touch",
    "break",
    "dx分数",
    "dx评分",
    "同步游玩",
    "完全同步",
)


def is_arcaea_screenshot(width: int, height: int) -> bool:
    """判断尺寸是否匹配 Arcaea 截图特征（横向、非高分辨率）。

    两种布局：平板截图宽高比 ≈ 2360:1640（~1.44）；手机横屏截图宽高比约 1.7~2.6（如 2400x1080）。
    """
    if width <= height:
        return False
    if max(width, height) > _ARCAEA_MAX_DIM:
        return False
    if (width, height) == ARCAEA_RESOLUTION:
        return True
    aspect = width / height
    if abs(aspect - _ARCAEA_ASPECT) <= _ARCAEA_ASPECT_TOLERANCE:
        return True
    return _ARCAEA_PHONE_ASPECT_MIN <= aspect <= _ARCAEA_PHONE_ASPECT_MAX


def classify_cabinet_from_ocr(ocr_result: list) -> str:
    """根据 OCR 文本判断街机游戏为 maimai / chunithm / unknown。"""
    text = " ".join(item[1] for item in (ocr_result or [])).casefold()
    for key in _CHUNITHM_KEYS:
        if key.casefold() in text:
            return "chunithm"
    for key in _MAIMAI_KEYS:
        if key.casefold() in text:
            return "maimai"
    return "unknown"


def _cabinet_color_features(image: QImage) -> tuple[float, float, float]:
    """返回 (R 均值, 蓝紫占比, 白像素占比)。"""
    small = image.scaled(48, 36)
    total = small.width() * small.height()
    r_sum = 0
    blue = 0
    white = 0
    for y in range(small.height()):
        for x in range(small.width()):
            color = small.pixel(x, y)
            r = (color >> 16) & 0xFF
            g = (color >> 8) & 0xFF
            b = color & 0xFF
            r_sum += r
            mx = max(r, g, b)
            mn = min(r, g, b)
            if b > r and b > g and (b - r) > 30:
                blue += 1
            if mx > 235 and mn > 210:
                white += 1
    return r_sum / total, blue / total, white / total


def _cabinet_color_features_np(image: np.ndarray) -> tuple[float, float, float]:
    """同 _cabinet_color_features，但直接吃 BGR numpy 数组。"""
    small = cv2.resize(image, (48, 36))
    b = small[:, :, 0].astype(int)
    g = small[:, :, 1].astype(int)
    r = small[:, :, 2].astype(int)
    mx = small.max(axis=2)
    mn = small.min(axis=2)
    blue = float(((b > r) & (b > g) & ((b - r) > 30)).mean())
    white = float(((mx > 235) & (mn > 210)).mean())
    return float(r.mean()), blue, white


def classify_cabinet_by_color(image: np.ndarray) -> str:
    """用色彩启发式判断 BGR 图像属于舞萌还是中二（不含 arcaea）。"""
    r_mean, blue_ratio, white_ratio = _cabinet_color_features_np(image)
    is_maimai = (
        (
            r_mean < _MAIMAI_R_MAX
            and blue_ratio > _MAIMAI_BLUE_MIN
            and white_ratio < _MAIMAI_WHITE_MAX
        )
        or blue_ratio > _MAIMAI_BLUE_HIGH
    )
    return "maimai" if is_maimai else "chunithm"


def classify(image_path: str | Path) -> str:
    """返回 game 标识之一：arcaea / maimai / chunithm / unknown。

    与识别流水线（pipeline.py）保持一致：优先按图片尺寸判断 Arcaea，
    街机游戏优先用 OCR 文字布局分类，文字特征缺失时回退色彩启发式。
    """
    image_path = str(image_path)
    qimage = QImage(image_path)
    if qimage.isNull():
        return "unknown"

    width, height = qimage.width(), qimage.height()

    # Arcaea：移动端/平板横向截图，尺寸特征明显。
    if is_arcaea_screenshot(width, height):
        return "arcaea"

    # 街机实拍照片（含经微信压缩的低分辨率图）：优先用 OCR 文字布局区分。
    bgr = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if bgr is not None:
        from src.recognizers.common import get_engine
        ocr_result, _ = get_engine()(bgr)
        game = classify_cabinet_from_ocr(ocr_result)
        if game != "unknown":
            return game

    # 文字特征缺失时回退到色彩启发式。
    return classify_cabinet_by_color(bgr) if bgr is not None else "unknown"
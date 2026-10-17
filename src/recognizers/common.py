"""识别器公共工具：屏幕定位、OCR 引擎、ROI 文本提取与难度/歌名匹配。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from src.core.paths import japan_ocr_dict, japan_ocr_model
from src.library.matcher import load_difficulties, normalize_title, search_titles

# ROI 使用 (x0, y0, x1, y1) 四个归一化比例，兼容不同分辨率与裁剪后的图片。
ROI = tuple[float, float, float, float]

# 结算画面里常出现的面板标签，不是歌名，需从歌名候选中剔除。
_PANEL_PREFIXES = ("track", "level", "lv")
_PANEL_LABELS = {
    "clear",
    "cleared",
    "achievement",
    "new.record",
    "newrecord",
    "mybest",
    "fullcombo",
    "allperfect",
    # 记录/达成率标签：简繁日三种写法都要覆盖（舞萌国服为简体，日服/OCR 常出繁体「新紀錄/達成率」）。
    "新纪录",
    "新記錄",
    "新纪录",
    "紀錄",
    "記錄",
    "記録",
    "我的最佳",
    "达成率",
    "達成率",
    "达成",
    "達成",
    "同步游玩",
    "通关",
    "通過",
    "曲目",
    "等级",
    "等級",
    "标准",
    "標準",
    "标準",
    "dx",
    "xg",
}

_engine: RapidOCR | None = None


def get_engine() -> RapidOCR:
    """返回进程内复用的 RapidOCR 引擎。"""
    global _engine
    if _engine is None:
        _engine = RapidOCR()
    return _engine


_jp_engine: RapidOCR | None = None


def get_japanese_engine() -> RapidOCR:
    """返回进程内复用的日文 OCR 引擎（复用中文检测/方向分类，仅识别模型换为日文）。

    用于中文模型读不出的彩色/描边艺术字日文标题的补充识别。
    """
    global _jp_engine
    if _jp_engine is None:
        _jp_engine = RapidOCR(
            rec_model_path=str(japan_ocr_model()),
            rec_keys_path=str(japan_ocr_dict()),
        )
    return _jp_engine


def load_image(path: str | Path) -> np.ndarray | None:
    """读取图片为 BGR 数组；Windows 下绕开 cv2.imread 的非 ASCII 路径限制。"""
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    return image if image is not None else None


def load_and_prepare(path: str | Path) -> np.ndarray | None:
    """读取图片并定位屏幕裁剪，供识别统一使用；读取失败返回 None。"""
    image = load_image(path)
    if image is None:
        return None
    screen = locate_screen(image)
    if screen is not None:
        x, y, w, h = screen
        return image[y : y + h, x : x + w]
    return image


def locate_circle(image: np.ndarray) -> tuple[int, int, int] | None:
    """定位舞萌的圆形主屏，返回 (圆心 x, 圆心 y, 半径)；找不到返回 None。"""
    height, width = image.shape[:2]
    scale = 1000.0 / max(height, width)
    small = cv2.resize(image, None, fx=scale, fy=scale)
    small_height, small_width = small.shape[:2]
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur = cv2.medianBlur(gray, 5)
    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=int(small_width * 0.5),
        param1=120,
        param2=50,
        minRadius=int(small_width * 0.2),
        maxRadius=int(small_width * 0.6),
    )
    if circles is None:
        return None
    # HoughCircles 按投票数排序，第一条是最强的主屏圆，不要按半径挑最大。
    cx, cy, radius = circles[0][0]
    cx, cy, radius = int(cx / scale), int(cy / scale), int(radius / scale)
    if radius < 0.15 * min(height, width):
        return None
    return cx, cy, radius


def circle_square_crop(image: np.ndarray) -> np.ndarray | None:
    """把舞萌圆形主屏裁成外接正方形；找不到圆返回 None。"""
    circle = locate_circle(image)
    if circle is None:
        return None
    cx, cy, radius = circle
    height, width = image.shape[:2]
    x = max(0, cx - radius)
    y = max(0, cy - radius)
    w = min(2 * radius, width - x)
    h = min(2 * radius, height - y)
    if w <= 0 or h <= 0:
        return None
    return image[y : y + h, x : x + w]


def locate_screen(image: np.ndarray) -> tuple[int, int, int, int] | None:
    """定位实拍照片里的屏幕区域，返回 (x, y, w, h)；找不到时返回 None。

    思路：街机屏幕明显亮于周围机台，用固定阈值二值化 + 最大连通域近似屏幕范围。
    固定阈值比 Otsu 更稳：Otsu 在国际服等「深色顶部 + 亮色下部」的画面上会把
    顶部的歌名/难度区域裁掉。
    这里只做轴对齐裁剪（样本基本为正拍），不做旋转/透视。
    """
    height, width = image.shape[:2]
    scale = 1200.0 / max(height, width)
    small = cv2.resize(image, None, fx=scale, fy=scale)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    _, binary = cv2.threshold(blur, 60, 255, cv2.THRESH_BINARY)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((13, 13), np.uint8))

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest)

    x = int(x / scale)
    y = int(y / scale)
    w = int(w / scale)
    h = int(h / scale)

    # 面积过小说明只是反光/亮块，不可信，回退整图。
    if w * h < 0.15 * width * height:
        return None

    x = max(0, x)
    y = max(0, y)
    w = min(w, width - x)
    h = min(h, height - y)
    if w <= 0 or h <= 0:
        return None
    return (x, y, w, h)


def _order_quad(points: np.ndarray) -> np.ndarray:
    """把 4 个角点排序为 [左上, 右上, 右下, 左下]。"""
    pts = np.array(points, dtype=np.float32).reshape(4, 2)
    ordered = np.zeros((4, 2), dtype=np.float32)
    total = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).ravel()
    ordered[0] = pts[np.argmin(total)]   # 左上：x+y 最小
    ordered[2] = pts[np.argmax(total)]   # 右下：x+y 最大
    ordered[1] = pts[np.argmin(diff)]    # 右上：y-x 最小
    ordered[3] = pts[np.argmax(diff)]    # 左下：y-x 最大
    return ordered


def detect_screen_quad(image: np.ndarray) -> np.ndarray | None:
    """定位屏幕四角（float32 4x2，顺序 左上/右上/右下/左下）；找不到返回 None。"""
    height, width = image.shape[:2]
    scale = 1200.0 / max(height, width)
    small = cv2.resize(image, None, fx=scale, fy=scale)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    _, binary = cv2.threshold(blur, 60, 255, cv2.THRESH_BINARY)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((13, 13), np.uint8))
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < 0.15 * small.shape[0] * small.shape[1]:
        return None
    peri = cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, 0.02 * peri, True).reshape(-1, 2)
    if len(approx) != 4:
        return None
    return _order_quad(approx) / scale


def rectify_tilted_screen(image: np.ndarray, min_angle: float = 7.0) -> np.ndarray | None:
    """把明显倾斜的矩形屏幕（中二）校正为轴对齐矩形；不需要校正时返回 None。

    仅当屏幕检测到的上边相对水平线倾斜超过 min_angle 度时才校正，避免影响正拍样本
    （返回 None 时调用方沿用原来的轴对齐裁剪）。舞萌为圆形屏幕，不在此处理。
    """
    quad = detect_screen_quad(image)
    if quad is None:
        return None
    top_left, top_right, bottom_right, bottom_left = quad
    angle = abs(np.degrees(np.arctan2(top_right[1] - top_left[1], top_right[0] - top_left[0])))
    while angle > 45.0:
        angle = abs(angle - 90.0)
    if angle < min_angle:
        return None
    width = max(np.linalg.norm(bottom_right - bottom_left), np.linalg.norm(top_right - top_left))
    height = max(np.linalg.norm(top_right - bottom_right), np.linalg.norm(top_left - bottom_left))
    out_w, out_h = int(round(float(width))), int(round(float(height)))
    if out_w < 50 or out_h < 50:
        return None
    destination = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype=np.float32
    )
    matrix = cv2.getPerspectiveTransform(quad.astype(np.float32), destination)
    return cv2.warpPerspective(image, matrix, (out_w, out_h))


@dataclass
class RecognitionResult:
    """一次识别的结果：歌名、难度、状态与候选。"""

    title: str | None
    difficulty: str | None
    status: str  # confirmed / pending / deferred
    title_candidates: list[tuple[str, float]] = field(default_factory=list)
    observed_title_text: str = ""


def _center(box: list) -> tuple[float, float]:
    xs = [point[0] for point in box]
    ys = [point[1] for point in box]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def collect_lines(
    ocr_result: list,
    roi: ROI,
    width: int,
    height: int,
) -> list[tuple[str, float, float]]:
    """收集 ROI 内的 OCR 文本行，返回按 y 排序的 (text, cy, cx)。"""
    x0, y0, x1, y1 = roi
    lines: list[tuple[str, float, float]] = []
    for box, text, _score in (ocr_result or []):
        cx, cy = _center(box)
        nx, ny = cx / width, cy / height
        if x0 <= nx <= x1 and y0 <= ny <= y1:
            lines.append((text, cy, cx))
    lines.sort(key=lambda item: (item[1], item[2]))
    return lines


def find_difficulty(
    lines: list[tuple[str, float, float]],
    game: str,
) -> tuple[str, float] | None:
    """从文本行中找难度，返回 (难度名, 行中心 y)；找不到返回 None。

    匹配强度排序：完全相等 > 互相包含 > 前缀；同级里选更长的名称，
    避免「Re:MASTER」被先命中成「MASTER」。
    """
    for text, cy, _cx in lines:
        norm = normalize_title(text)
        if not norm:
            continue
        best_key: tuple[int, int] | None = None
        best: tuple[str, float] | None = None
        for item in load_difficulties(game):
            for candidate in [item["name"], *item.get("aliases", [])]:
                cn = normalize_title(candidate)
                if not cn:
                    continue
                if cn == norm:
                    rank = 0
                elif cn in norm:
                    rank = 1
                elif len(norm) >= 3 and norm in cn:
                    # OCR 截断（如 MAST -> MASTER）才允许反向包含，避免单字符误命中。
                    rank = 1
                elif len(cn) >= 3 and norm.startswith(cn[:3]):
                    rank = 2
                else:
                    continue
                key = (rank, -len(cn))
                if best_key is None or key < best_key:
                    best_key = key
                    best = (item["name"], cy)
        if best is not None:
            return best
    return None


def is_panel_label(text: str, game: str) -> bool:
    """判断文本是否为面板标签（TRACK/LEVEL/难度名/纯数字），用于从歌名候选中剔除。"""
    norm = normalize_title(text)
    if not norm:
        return True
    if norm in _PANEL_LABELS or norm.startswith(_PANEL_PREFIXES):
        return True

    # 含百分号的一定是达成率/数值（如 96.8010% / 100.9000%），不是歌名（曲库无含 % 的歌名）。
    if "%" in norm:
        return True

    # 「新紀錄/新記録」的 OCR 变体：末字被误读成 泉/景/屋/子/禄 等，形如「新紀泉」「新記景」。
    # 曲库无「新紀…/新記…」开头的歌名，按前两字剔除，避免这类噪声混进歌名候选与学习别名。
    if norm[:2] in {"新紀", "新記", "新纪", "新记"}:
        return True

    # 单个 ASCII 字符（如「+」「X」「P」）通常是噪声或图标残片，不是歌名。
    if len(norm) == 1 and norm.isascii():
        return True

    has_letter = any(ch.isalpha() or "\u4e00" <= ch <= "\u9fff" for ch in norm)
    # 纯符号（如「+」「%」）与纯数字（如等级 14、13*）都不是歌名。
    if not has_letter:
        return True

    for item in load_difficulties(game):
        for candidate in [item["name"], *item.get("aliases", [])]:
            cn = normalize_title(candidate)
            if cn and cn == norm:
                return True
    return False


def rank_title_candidates(
    game: str,
    lines: list[tuple[str, float, float]],
    limit: int = 8,
) -> tuple[str | None, str, list[tuple[str, float]], str]:
    """把 ROI 内的文本行组合成查询并聚合曲库候选。

    返回 (最佳歌名, 状态, 候选, 识别到的原始文本)；原始文本供算法实时优化评估。
    """
    texts = [text for text, _cy, _cx in lines if not is_panel_label(text, game)]
    if not texts:
        return None, "deferred", [], ""

    queries: list[str] = []
    queries.append(" ".join(texts))
    for k in range(1, min(len(texts), 4) + 1):
        queries.append(" ".join(texts[:k]))
    queries.extend(texts)

    best_by_title: dict[str, float] = {}
    best_query_len: dict[str, int] = {}
    for query in queries:
        query_len = len(normalize_title(query))
        for title, score in search_titles(game, query, limit=limit):
            if score > best_by_title.get(title, 0.0):
                best_by_title[title] = score
                best_query_len[title] = query_len

    ranked = sorted(best_by_title.items(), key=lambda item: item[1], reverse=True)
    best_title: str | None = None
    status = "deferred"
    if ranked:
        top_title, best_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        # 自动确认要求：分数够高、查询文本足够长、且没有接近的竞争候选，
        # 避免短片段（如单个「歌」字）误命中多首歌。
        if best_score >= 0.75 and best_query_len.get(top_title, 0) >= 2 and second_score < best_score - 0.05:
            best_title = top_title
            status = "confirmed"
        elif best_score >= 0.45:
            status = "pending"

    return best_title, status, ranked[:5], " ".join(texts)
_STATUS_RANK = {"confirmed": 3, "pending": 2, "deferred": 1, "unknown": 0}


def filter_lines_by_roi(lines, roi, width, height):
    """从 [(text, cy, cx)] 中筛出落在 ROI 内的行，按 (cy, cx) 排序。"""
    x0, y0, x1, y1 = roi
    out = []
    for text, cy, cx in lines:
        nx, ny = cx / width, cy / height
        if x0 <= nx <= x1 and y0 <= ny <= y1:
            out.append((text, cy, cx))
    out.sort(key=lambda item: (item[1], item[2]))
    return out


def japanese_lines(image) -> list[tuple[str, float, float]]:
    """用日文模型对整幅图再 OCR，返回 [(text, cy, cx)]（图像坐标）。"""
    result, _ = get_japanese_engine()(image)
    lines = []
    for box, text, _score in (result or []):
        cx, cy = _center(box)
        lines.append((text, cy, cx))
    return lines


def rank_title_candidates_with_japanese(game, view, title_lines, roi, width, height, min_cy=None):
    """先按现有 OCR 行排序；未自动确认时用日文模型补充识别，合并后再排序。

    返回 (最佳歌名, 状态, 候选, 识别到的原始文本)。日文模型仅在中文模型未自动确认时启用，
    避免对已正确识别（正拍）的样本产生影响。
    """
    title, status, candidates, observed = rank_title_candidates(game, title_lines)
    if status == "confirmed":
        return title, status, candidates, observed

    try:
        jp_lines = filter_lines_by_roi(japanese_lines(view), roi, width, height)
    except Exception:  # noqa: BLE001 - 日文模型缺失/加载失败时退回中文结果
        return title, status, candidates, observed
    if min_cy is not None:
        jp_lines = [line for line in jp_lines if line[1] > min_cy]
    if not jp_lines:
        return title, status, candidates, observed

    merged = list(title_lines) + jp_lines
    t2, s2, c2, o2 = rank_title_candidates(game, merged)
    if _STATUS_RANK.get(s2, 0) > _STATUS_RANK.get(status, 0):
        return t2, s2, c2, o2
    return title, status, candidates, observed

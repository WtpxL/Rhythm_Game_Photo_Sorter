"""曲库模糊匹配：把 OCR 文本匹配到本地曲库歌名。

曲库来源为程序同级的 SongLists/（见 src/library/store.py），文件缺失时回退内置曲库。
"""

from __future__ import annotations

import difflib
import json
import unicodedata

from src.core.paths import difficulties_json
from src.library import store

_STRIP = " 　\t\r\n"

# 截断歌名（右侧被立绘遮挡等）常只能读到前半段，且截断处的末字容易被 OCR 读错：
# 例如真实歌名「Lost Emotion feat. nomico」只读到「Lost Emc」。此时把读到的片段与
# 歌名「同长度前缀」比对，高度吻合就按前缀命中给分，避免这种漏判。
# 门槛从严（较长 + 高度吻合），以免短噪声片段误命中。
_PREFIX_MIN_LEN = 4
_PREFIX_RATIO = 0.8


def normalize_title(text: str) -> str:
    """NFKC 归一化 + 小写 + 去空白，吸收全半角/大小写差异。"""
    norm = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in norm if ch not in _STRIP)


def similarity(a: str, b: str) -> float:
    na = normalize_title(a)
    nb = normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # 仅「前缀包含」才给高置信加成（如 OCR 只读到歌名前半段 Aeth → Aether Crest: Astral）。
    # 中间的偶然子串不给加成，避免曲师名里的 "un" 误命中短曲名 Un —— 这类改由 difflib 处理。
    if na.startswith(nb) or nb.startswith(na):
        shorter = min(len(na), len(nb))
        longer = max(len(na), len(nb))
        return 0.7 + 0.3 * shorter / longer
    # 近似前缀：长度不同、且较短方与较长方的同长度前缀高度吻合（截断处末字被读错也算）。
    if len(na) != len(nb):
        short, long = (na, nb) if len(na) < len(nb) else (nb, na)
        if len(short) >= _PREFIX_MIN_LEN:
            ratio = difflib.SequenceMatcher(None, short, long[: len(short)]).ratio()
            if ratio >= _PREFIX_RATIO:
                return 0.7 + 0.3 * (len(short) / len(long)) * ratio
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _learned_aliases(game: str) -> dict[str, list[str]]:
    """读取算法实时优化沉淀的学习别名 {歌名: [片段]}（延迟导入避免循环依赖）。"""
    from src.library.learning import load_learned_aliases

    try:
        return load_learned_aliases(game)
    except Exception:  # noqa: BLE001 - 学习库不可用时不影响正常匹配
        return {}


def load_difficulties(game: str) -> list[dict]:
    """返回某游戏的难度词表 [{name, aliases}]。"""
    with open(difficulties_json(), encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get(game, [])


def search_titles(
    game: str,
    query: str,
    limit: int = 8,
    threshold: float = 0.35,
) -> list[tuple[str, float]]:
    """返回按相似度降序的歌名候选 [(title, score)]，低于阈值的不返回。

    评分同时考虑曲库歌名、曲库别名与算法优化学习到的别名，取最高相似度。
    """
    rows = store.load_songs(game)
    learned = _learned_aliases(game)

    best_by_title: dict[str, float] = {}
    for title, aliases in rows:
        score = similarity(query, title)
        for alias in aliases:
            score = max(score, similarity(query, alias))
        for alias in learned.get(title, []):
            score = max(score, similarity(query, alias))
        if score >= threshold:
            best_by_title[title] = score

    ranked = sorted(best_by_title.items(), key=lambda item: item[1], reverse=True)
    return [(title, round(score, 3)) for title, score in ranked[:limit]]

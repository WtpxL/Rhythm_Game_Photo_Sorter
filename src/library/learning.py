"""识别算法实时优化：评估人工确认的歌名是否值得学习，并沉淀为可复用别名。

评估（evaluate_learning）：
- 值得学：OCR 读到的片段与最终歌名存在包含/相似关系（歌名部分可见，人工补齐的是残缺部分）。
- 不值得学：OCR 完全没读到文本、或读到的内容与歌名差异过大（歌名被完全遮挡）。

存储：学习记录外置于 config/LearnLogs/<game>.json（与 SongLists 同级的 config/ 下），
每个游戏一个可读文件，结构如下，便于查看、编辑与备份：

{
  "game": "maimai",
  "name": "舞萌",
  "updated_at": "2026-10-17T...",
  "records": [
    {"alias": "识别片段", "title": "歌名", "reason": "歌名部分可见…", "created_at": "2026-10-17T..."}
  ]
}

曲库匹配（matcher.search_titles）会把学习到的别名一并计入相似度，下次出现相同片段即可自动命中。
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from src.core.paths import learn_logs_dir
from src.library.matcher import normalize_title, similarity

# 学习门槛：OCR 片段至少这么长才值得登记，避免把单字噪声学成别名。
MIN_OBSERVED_LEN = 2
# 模糊但可辨的相似度门槛：达到即认为歌名「部分可见/可辨」，值得学习。
BLURRY_THRESHOLD = 0.45

GAMES = ("arcaea", "maimai", "chunithm")
GAME_NAMES = {"arcaea": "Arcaea", "maimai": "舞萌", "chunithm": "中二节奏"}
FILENAMES = {"arcaea": "Arcaea.json", "maimai": "maimai.json", "chunithm": "chunithm.json"}


@dataclass
class LearningDecision:
    """一次人工输入的「是否值得学习」评估结果。"""

    worth: bool
    reason: str
    alias: str | None = None


def log_file(game: str):
    """某游戏学习记录文件的路径。"""
    return learn_logs_dir() / FILENAMES[game]


def _visible_len(text: str) -> int:
    """用于门槛判断的有效字符数：NFKC 归一化后去掉空白。"""
    norm = unicodedata.normalize("NFKC", text or "")
    return len("".join(ch for ch in norm if not ch.isspace()))


def _fragments(observed: str) -> list[str]:
    """把识别文本切成候选片段：整体 + 按空白切分的词。

    歌名区域常同时读到「歌名 + 曲师」（如 "Aeth void (Moun"）；整体与歌名比对会被曲师
    稀释，故逐片段评估，取最贴合歌名的片段来学习。
    """
    text = (observed or "").strip()
    if not text:
        return []
    parts = [text]
    parts.extend(tok for tok in re.split(r"\s+", text) if tok)
    return parts


def evaluate_learning(game: str, observed: str, title: str) -> LearningDecision:
    """评估这次人工输入是否值得拿来学习优化。

    observed 为本次 OCR 在歌名区域读到的原始文本，title 为人工确认的最终歌名。
    逐片段（整体/词）与歌名比对，取相似度最高的片段：只要有一条片段明显贴合歌名
    （前缀包含或相似度达标），即认为值得学习，并学习该片段为别名。
    """
    del game  # 目前三游戏共用同一套判定规则，保留形参便于以后按游戏细分。
    tgt = normalize_title(title or "")
    if not tgt:
        return LearningDecision(False, "尚未填写歌名")
    text = (observed or "").strip()
    if not text:
        return LearningDecision(False, "本次未读出歌名文本，标题可能完全被遮挡")
    if normalize_title(text) == tgt:
        return LearningDecision(False, "识别文本与确认歌名一致，无需学习")

    best_frag: str | None = None
    best_score = 0.0
    for frag in _fragments(text):
        nf = normalize_title(frag)
        if not nf or nf == tgt:
            continue
        if _visible_len(frag) < MIN_OBSERVED_LEN:
            continue
        score = similarity(frag, title)
        if score > best_score:
            best_score = score
            best_frag = frag

    if best_frag is None:
        return LearningDecision(False, "识别文本过短（仅个别字符），学习价值不足")

    if best_score >= BLURRY_THRESHOLD:
        if best_score >= 0.7:
            reason = "歌名部分可见（识别片段与曲库前缀命中）"
        else:
            reason = f"歌名模糊但可辨（相似度 {best_score:.2f}）"
        return LearningDecision(True, reason, best_frag.strip())

    return LearningDecision(
        False, f"识别文本与歌名差异过大（相似度 {best_score:.2f}），可能被完全遮挡"
    )


def _read_records(game: str) -> list[dict]:
    path = log_file(game)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        return []
    return [r for r in records if isinstance(r, dict)]


def _write_records(game: str, records: list[dict]) -> None:
    directory = learn_logs_dir()
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "game": game,
        "name": GAME_NAMES.get(game, game),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "records": records,
    }
    log_file(game).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def record_learned(game: str, alias: str, title: str, reason: str = "") -> bool:
    """把一次学习登记的 (片段 -> 歌名) 写入 config/LearnLogs/；重复登记返回 False。"""
    alias = (alias or "").strip()
    title = (title or "").strip()
    if not alias or not title:
        return False
    records = _read_records(game)
    for record in records:
        if str(record.get("alias", "")) == alias and str(record.get("title", "")) == title:
            return False
    records.append(
        {
            "alias": alias,
            "title": title,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _write_records(game, records)
    return True


def load_learned_aliases(game: str) -> dict[str, list[str]]:
    """返回某游戏已学习的别名映射 {歌名: [片段, ...]}。"""
    mapping: dict[str, list[str]] = {}
    for record in _read_records(game):
        title = str(record.get("title", "")).strip()
        alias = str(record.get("alias", "")).strip()
        if title and alias:
            mapping.setdefault(title, []).append(alias)
    return mapping


def list_learned(game: str | None = None) -> list[dict]:
    """列出学习记录（新→旧），供界面查看。每项含 game/alias/title/reason/created_at。"""
    games = [game] if game else list(GAMES)
    rows: list[dict] = []
    for g in games:
        for record in _read_records(g):
            rows.append(
                {
                    "game": g,
                    "alias": str(record.get("alias", "")),
                    "title": str(record.get("title", "")),
                    "reason": str(record.get("reason", "")),
                    "created_at": str(record.get("created_at", "")),
                }
            )
    rows.sort(key=lambda row: row["created_at"], reverse=True)
    return rows


def count_learned(game: str | None = None) -> int:
    """学习记录条数。"""
    return len(list_learned(game))


def clear_learned(game: str | None = None) -> int:
    """清空学习记录（可指定游戏），返回删除条数。"""
    games = [game] if game else list(GAMES)
    removed = 0
    for g in games:
        removed += len(_read_records(g))
        _write_records(g, [])
    return removed

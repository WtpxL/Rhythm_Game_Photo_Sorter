"""图片索引：SQLite 中的图片记录存取与搜索。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.core.paths import index_db

_UNSET = object()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(index_db())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """建表（幂等）。"""
    index_db().parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL UNIQUE,
            organized_path TEXT,
            game TEXT NOT NULL,
            title TEXT,
            difficulty TEXT,
            note TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'confirmed',
            observed_text TEXT NOT NULL DEFAULT '',
            imported_at TEXT NOT NULL
        )
        """
    )
    # 迁移：早期版本没有 observed_text 列（识别到的原始文本，供检索页编辑学习）。
    columns = [row[1] for row in conn.execute('PRAGMA table_info(images)').fetchall()]
    if 'observed_text' not in columns:
        conn.execute("ALTER TABLE images ADD COLUMN observed_text TEXT NOT NULL DEFAULT ''")
    _migrate_organized_key(conn)
    conn.commit()
    conn.close()


def _migrate_organized_key(conn: sqlite3.Connection) -> None:
    """把已确认（已移动）记录的唯一键归位到移动后的实际路径。

    历史版本里确认记录仍以原 input 路径为唯一键；由于整理会把文件移出 input，
    重新导入同名图片时会命中这条旧记录，被误判为「已处理」。这里把这类记录的唯一键
    改写到 organized_path（文件实际所在位置），与「索引以移动后路径为唯一键」的设计一致。
    """
    rows = conn.execute(
        "SELECT id, source_path, organized_path FROM images "
        "WHERE status='confirmed' AND organized_path IS NOT NULL AND organized_path <> source_path"
    ).fetchall()
    for row_id, _source, organized in rows:
        existing = conn.execute(
            "SELECT id FROM images WHERE source_path=?", (organized,)
        ).fetchone()
        if existing is not None and existing[0] != row_id:
            conn.execute("DELETE FROM images WHERE id=?", (row_id,))
        else:
            conn.execute(
                "UPDATE images SET source_path=? WHERE id=?", (organized, row_id)
            )


@dataclass
class ImageRecord:
    id: int
    source_path: str
    organized_path: str | None
    game: str
    title: str | None
    difficulty: str | None
    note: str
    status: str
    observed_text: str
    imported_at: str


def _row_to_record(row: sqlite3.Row) -> ImageRecord:
    return ImageRecord(
        id=row["id"],
        source_path=row["source_path"],
        organized_path=row["organized_path"],
        game=row["game"],
        title=row["title"],
        difficulty=row["difficulty"],
        note=row["note"],
        status=row["status"],
        observed_text=row["observed_text"],
        imported_at=row["imported_at"],
    )


def upsert(
    source_path: str | Path,
    game: str,
    title: str | None = None,
    difficulty: str | None = None,
    note: str = "",
    status: str = "confirmed",
    organized_path: str | Path | None = None,
    observed_text: str = "",
) -> None:
    """插入或更新一条图片记录（以原图路径为唯一键）。

    observed_text 为空字符串时保持已有值不变（避免覆盖此前识别到的原始文本）。
    """
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    conn.execute(
        """
        INSERT INTO images(
            source_path, organized_path, game, title, difficulty, note, status,
            observed_text, imported_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_path) DO UPDATE SET
            organized_path=excluded.organized_path,
            game=excluded.game,
            title=excluded.title,
            difficulty=excluded.difficulty,
            note=excluded.note,
            status=excluded.status,
            observed_text=CASE WHEN excluded.observed_text <> ''
                               THEN excluded.observed_text ELSE images.observed_text END,
            imported_at=excluded.imported_at
        """,
        (
            str(source_path),
            str(organized_path) if organized_path else None,
            game,
            title,
            difficulty,
            note,
            status,
            observed_text or "",
            now,
        ),
    )
    conn.commit()
    conn.close()


def list_records(
    game: str | None = None,
    query: str = "",
    difficulty: str | None = None,
    status: str | None = None,
) -> list[ImageRecord]:
    """按游戏/歌名/备注/难度筛选图片记录，按导入时间倒序。"""
    init_db()
    conditions: list[str] = []
    params: list[str] = []
    if game:
        conditions.append("game = ?")
        params.append(game)
    if difficulty:
        conditions.append("difficulty = ?")
        params.append(difficulty)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if query.strip():
        like = f"%{query.strip()}%"
        conditions.append("(title LIKE ? OR note LIKE ?)")
        params.extend([like, like])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    conn = _connect()
    rows = conn.execute(
        f"SELECT * FROM images {where} ORDER BY imported_at DESC, id DESC",
        params,
    ).fetchall()
    conn.close()
    return [_row_to_record(row) for row in rows]


def update_record(
    source_path: str | Path,
    *,
    game: str | None = _UNSET,
    title: str | None = _UNSET,
    difficulty: str | None = _UNSET,
    note: str | None = _UNSET,
    status: str | None = _UNSET,
    organized_path: str | Path | None = _UNSET,
    new_source_path: str | Path | None = _UNSET,
) -> None:
    """更新一条记录的可选字段；提供 new_source_path 时一并改写唯一键。"""
    init_db()
    assignments: list[str] = []
    params: list[str] = []
    if game is not _UNSET:
        assignments.append("game=?")
        params.append(game)
    if title is not _UNSET:
        assignments.append("title=?")
        params.append(title)
    if difficulty is not _UNSET:
        assignments.append("difficulty=?")
        params.append(difficulty)
    if note is not _UNSET:
        assignments.append("note=?")
        params.append(note)
    if status is not _UNSET:
        assignments.append("status=?")
        params.append(status)
    if organized_path is not _UNSET:
        assignments.append("organized_path=?")
        params.append(str(organized_path) if organized_path is not None else None)
    if new_source_path is not _UNSET:
        assignments.append("source_path=?")
        params.append(str(new_source_path) if new_source_path is not None else None)
    if not assignments:
        return
    assignments.append("imported_at=?")
    params.append(datetime.now(timezone.utc).isoformat())
    params.append(str(source_path))

    conn = _connect()
    conn.execute(
        f"UPDATE images SET {', '.join(assignments)} WHERE source_path=?",
        params,
    )
    conn.commit()
    conn.close()


def get_record(source_path: str | Path) -> ImageRecord | None:
    init_db()
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM images WHERE source_path=?",
        (str(source_path),),
    ).fetchone()
    conn.close()
    return _row_to_record(row) if row else None


def delete_record(source_path: str | Path) -> None:
    """删除一条图片记录（不存在则无操作）。"""
    init_db()
    conn = _connect()
    conn.execute("DELETE FROM images WHERE source_path=?", (str(source_path),))
    conn.commit()
    conn.close()


def update_note(source_path: str | Path, note: str) -> None:
    init_db()
    conn = _connect()
    conn.execute(
        "UPDATE images SET note=? WHERE source_path=?",
        (note, str(source_path)),
    )
    conn.commit()
    conn.close()


def count_records() -> int:
    init_db()
    conn = _connect()
    total = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    conn.close()
    return total

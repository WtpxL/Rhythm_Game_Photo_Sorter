"""路径解析：兼容源码运行与 PyInstaller 打包。

打包为 one-folder 绿色版后：

- 只读资源（曲库、难度词表等）随程序解包到 ``sys._MEIPASS`` 内。
- 可写数据（图片索引、曲库、学习记录、整理目录）放在可执行文件同级目录，便于绿色分发；
  其中曲库与学习记录位于 config/ 下（config/SongLists/、config/LearnLogs/），方便人工查看与修改。
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包环境。"""
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """应用根目录：打包后为 exe 所在目录，源码运行为项目根目录。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundled_root() -> Path:
    """只读资源根目录：打包后为解包目录，源码运行为项目根目录。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_root()))
    return app_root()


def library_db() -> Path:
    """本地曲库 SQLite 路径（只读）。"""
    return bundled_root() / "data" / "library.db"


def difficulties_json() -> Path:
    """难度词表 JSON 路径（只读）。"""
    return bundled_root() / "data" / "difficulties.json"


def japan_ocr_model() -> Path:
    """日文 OCR 识别模型路径（只读资源）。"""
    return bundled_root() / "data" / "ocr_japan" / "japan_PP-OCRv4_rec_mobile.onnx"


def japan_ocr_dict() -> Path:
    """日文 OCR 字符表路径（只读资源）。"""
    return bundled_root() / "data" / "ocr_japan" / "japan_dict.txt"


def config_dir() -> Path:
    """配置目录：程序同级的 config/，存放曲库与学习记录等外置数据。"""
    return app_root() / "config"


def song_lists_dir() -> Path:
    """外置曲库目录：config/SongLists/，存放各游戏可编辑的歌名库文件。"""
    return config_dir() / "SongLists"


def learn_logs_dir() -> Path:
    """学习记录目录：config/LearnLogs/，存放算法实时优化沉淀的学习记录。"""
    return config_dir() / "LearnLogs"


def index_db() -> Path:
    """图片索引 SQLite 路径（可写，程序同级 config/index.db）。"""
    return config_dir() / "index.db"


def organized_root() -> Path:
    """已确认图片的整理根目录。"""
    return app_root() / "sorted"


def input_dir() -> Path:
    """默认输入目录：放待处理的原图。"""
    return app_root() / "input"


def sorted_dir() -> Path:
    """默认输出目录：整理后的图片。"""
    return app_root() / "sorted"

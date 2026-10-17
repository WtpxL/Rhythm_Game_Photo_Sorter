# -*- mode: python ; coding: utf-8 -*-

"""PyInstaller 打包配置：Windows 绿色目录（one-folder）。"""

import os

from PyInstaller.utils.hooks import collect_data_files


def _drop_foreign_icu(binaries):
    """剔除从 PATH（如 Poppler）误收集的外来 ICU DLL。

    PySide6 6.12 依赖 Windows 自带的 ICU（System32），并不自带 ICU DLL；
    打包时若从环境 PATH 捡到不兼容的 icuuc/icudt DLL，会导致 Qt 加载失败
    （错误 127：找不到指定的程序）。
    """
    return [
        entry
        for entry in binaries
        if not os.path.basename(entry[0]).lower().startswith("icu")
    ]


datas = [
    # 内置曲库与难度词表。
    # 曲库现为「外置 + 兜底」：运行时优先读 exe 同级的 SongLists/（可人工编辑），
    # 缺失时用这里的 library.db 生成一份；difficulties.json 仍随程序解包（只读）。
    ("data/library.db", "data"),
    ("data/difficulties.json", "data"),
    # 日文 OCR 识别模型与字符表（用于彩色/艺术字日文标题的补充识别）。
    ("data/ocr_japan/japan_PP-OCRv4_rec_mobile.onnx", "data/ocr_japan"),
    ("data/ocr_japan/japan_dict.txt", "data/ocr_japan"),
]
# RapidOCR 默认模型与配置，保持包内相对路径以正常加载。
datas += collect_data_files("rapidocr_onnxruntime")


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    noarchive=False,
)
a.binaries = _drop_foreign_icu(a.binaries)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="音游成绩图分类工具",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="音游成绩图分类工具",
)

"""打包后干净环境自检：不开启图形界面，逐项校验「无开发环境依赖」。

检查项：
1. 只读资源随包解包（内置曲库、难度词表、日文 OCR 模型与字符表）
2. 程序同级可写目录（input/sorted/config）与外置曲库生成/加载
3. 图片索引 config/index.db 初始化与查询
4. 中/日文 OCR 引擎（RapidOCR）加载并实际推理一张合成图
5. 可选：对一张真实样本图跑完整识别流水线（--sample 指定）

打包版为窗口程序（无控制台），因此报告同时写入程序同级的 selfcheck.log；
任一检查失败返回非零退出码，便于在干净环境验证绿色分发。
"""

from __future__ import annotations

import sys
from pathlib import Path


class _Tee:
    """把输出同时写入若干流（控制台 + 日志文件），跳过 None 流。"""

    def __init__(self, *streams) -> None:
        self._streams = [s for s in streams if s is not None]

    def write(self, text: str) -> int:
        for stream in self._streams:
            try:
                stream.write(text)
                stream.flush()
            except Exception:  # noqa: BLE001 - 输出流失败不应中断自检
                pass
        return len(text)

    def flush(self) -> None:
        for stream in self._streams:
            try:
                stream.flush()
            except Exception:  # noqa: BLE001
                pass


class _Report:
    """收集检查结果并统计失败项。"""

    def __init__(self) -> None:
        self.failures = 0
        self.checks = 0

    def ok(self, label: str, detail: str = "") -> bool:
        self.checks += 1
        print("[ OK ] %s%s" % (label, (" — " + detail) if detail else ""))
        return True

    def fail(self, label: str, detail: str = "") -> bool:
        self.checks += 1
        self.failures += 1
        print("[FAIL] %s%s" % (label, (" — " + detail) if detail else ""))
        return False

    def check(self, cond: bool, label: str, detail: str = "") -> bool:
        return self.ok(label, detail) if cond else self.fail(label, detail)


def _run_pipeline_sample(rep: _Report, sample: str) -> None:
    print("\n-- 5. 样本识别（完整流水线）--")
    from src.recognizers.pipeline import recognize_image

    path = Path(sample)
    if not rep.check(path.is_file(), "样本文件存在", str(path)):
        return
    try:
        game, result = recognize_image(str(path))
    except Exception as exc:  # noqa: BLE001 - 自检需捕获任何异常并报告
        rep.fail("recognize_image", repr(exc))
        return
    if result is None:
        rep.fail("recognize_image", "未返回识别结果")
        return
    rep.ok(
        "recognize_image",
        "game=%s title=%s difficulty=%s status=%s"
        % (game, result.title, result.difficulty, result.status),
    )


def run_selfcheck(sample: str | None = None) -> int:
    """执行全部自检项，返回进程退出码（0 成功）。"""
    from src.core import paths

    log_path = paths.app_root() / "selfcheck.log"
    log_file = open(log_path, "w", encoding="utf-8")
    real_stdout = sys.stdout
    sys.stdout = _Tee(real_stdout, log_file)
    try:
        return _run(paths, sample)
    finally:
        sys.stdout = real_stdout
        log_file.close()


def _run(paths, sample: str | None) -> int:
    rep = _Report()
    print("=" * 64)
    print("音游成绩图分类工具 · 干净环境自检")
    print("=" * 64)
    print("frozen      : %s" % paths.is_frozen())
    print("app_root    : %s" % paths.app_root())
    print("bundled_root: %s" % paths.bundled_root())
    print("python      : %s" % sys.version.split()[0])

    # 1. 只读资源
    print("\n-- 1. 只读资源（随包解包）--")
    for label, p in [
        ("内置曲库 library.db", paths.library_db()),
        ("难度词表 difficulties.json", paths.difficulties_json()),
        ("日文 OCR 模型", paths.japan_ocr_model()),
        ("日文 OCR 字符表", paths.japan_ocr_dict()),
    ]:
        rep.check(p.is_file(), label, str(p))

    # 2. 可写目录与外置曲库
    print("\n-- 2. 可写目录与外置曲库 --")
    try:
        paths.input_dir().mkdir(parents=True, exist_ok=True)
        paths.sorted_dir().mkdir(parents=True, exist_ok=True)
        paths.learn_logs_dir().mkdir(parents=True, exist_ok=True)
        rep.ok("input/sorted/config 目录", str(paths.config_dir()))
    except OSError as exc:
        rep.fail("input/sorted/config 目录", str(exc))

    from src.library.store import ensure_song_lists, stats

    try:
        created = ensure_song_lists()
        rep.ok("生成外置曲库", ("、".join(created) if created else "已存在，无需生成"))
    except OSError as exc:
        rep.fail("生成外置曲库", str(exc))

    try:
        st = stats()
        rep.check(st["total"] > 0, "曲库总览",
                  "共 %d 首，更新时间 %s" % (st["total"], st["updated_at"]))
        for game, info in st["games"].items():
            rep.check(
                info["total"] > 0,
                "  · %s" % game,
                "%d 首 / 别名 %d（%s）" % (info["total"], info["with_alias"], info["file"]),
            )
    except Exception as exc:  # noqa: BLE001
        rep.fail("曲库总览", repr(exc))

    # 3. 图片索引
    print("\n-- 3. 图片索引 --")
    from src.db import index as image_index

    try:
        image_index.init_db()
        rep.ok("config/index.db 初始化", str(paths.index_db()))
        rep.ok("索引查询", "当前 %d 条记录" % image_index.count_records())
    except Exception as exc:  # noqa: BLE001
        rep.fail("config/index.db 初始化", repr(exc))

    # 4. OCR 引擎（中/日文）
    print("\n-- 4. OCR 引擎 --")
    import cv2
    import numpy as np

    from src.recognizers import common

    canvas = np.full((96, 384, 3), 255, dtype=np.uint8)
    cv2.putText(canvas, "TRACK 1  ABC", (12, 64), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 2)

    try:
        engine = common.get_engine()
        engine(canvas)
        rep.ok("中文 OCR 引擎", "RapidOCR PP-OCRv4(ch) 加载并推理成功")
    except Exception as exc:  # noqa: BLE001
        rep.fail("中文 OCR 引擎", repr(exc))

    try:
        jp = common.get_japanese_engine()
        jp(canvas)
        rep.ok("日文 OCR 引擎", "japan_PP-OCRv4 加载并推理成功")
    except Exception as exc:  # noqa: BLE001
        rep.fail("日文 OCR 引擎", repr(exc))

    # 5. 可选样本
    if sample:
        _run_pipeline_sample(rep, sample)

    # 汇总
    print("\n" + "=" * 64)
    if rep.failures:
        print("自检结果：失败（%d/%d 项未通过）" % (rep.failures, rep.checks))
        print("报告已写入：%s" % (paths.app_root() / "selfcheck.log"))
        return 1
    print("自检结果：通过（%d 项全部正常）" % rep.checks)
    print("报告已写入：%s" % (paths.app_root() / "selfcheck.log"))
    return 0

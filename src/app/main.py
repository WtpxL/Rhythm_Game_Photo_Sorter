"""应用入口。"""

from __future__ import annotations

import sys


def _run_gui() -> int:
    from PySide6.QtWidgets import QApplication

    from src.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("音游成绩图分类查询工具")
    window = MainWindow()
    window.show()
    return app.exec()


def main() -> int:
    """命令行入口：默认启动图形界面；``--selfcheck`` 执行干净环境自检。"""
    argv = sys.argv[1:]

    if "--selfcheck" in argv:
        sample = None
        if "--sample" in argv:
            idx = argv.index("--sample")
            if idx + 1 < len(argv):
                sample = argv[idx + 1]
        from src.app.selfcheck import run_selfcheck

        return run_selfcheck(sample)

    return _run_gui()


if __name__ == "__main__":
    raise SystemExit(main())

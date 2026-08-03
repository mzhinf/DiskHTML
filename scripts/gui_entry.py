"""PyInstaller 入口：无参数启动生成界面，带参数执行 HTML 快照命令。"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from diskhtml.exe_cli import main as command_main
from diskhtml.ui import main as gui_main


def main(argv: Sequence[str] | None = None) -> int:
    """按参数选择图形界面或精简命令行 HTML 工作流。"""

    arguments = list(sys.argv[1:] if argv is None else argv)
    return command_main(arguments) if arguments else gui_main()


if __name__ == "__main__":
    raise SystemExit(main())

"""PyInstaller 入口：无参数启动生成界面，带参数执行 HTML 快照命令。"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from diskhtml._exe_config import ensure_exe_config
from diskhtml.config import load_config
from diskhtml.exe_cli import main as command_main
from diskhtml.ui import main as gui_main


def main(argv: Sequence[str] | None = None) -> int:
    """准备 EXE 默认配置，并按参数选择图形界面或精简命令行工作流。

    两种入口共享同一个 EXE 同级默认配置；命令行显式传入 ``--config``
    时仍由参数解析器覆盖这里注入的默认路径。
    """

    arguments = list(sys.argv[1:] if argv is None else argv)
    config_path = ensure_exe_config()
    if arguments:
        return command_main(arguments, default_config=config_path)
    return gui_main(load_config(config_path).scan)


if __name__ == "__main__":
    raise SystemExit(main())

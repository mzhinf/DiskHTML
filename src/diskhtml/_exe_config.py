"""管理冻结 EXE 的内置配置模板和外部默认配置。"""

from __future__ import annotations

import sys
from pathlib import Path

_PACKAGED_CONFIG = Path("config") / "config.example.toml"
_EXTERNAL_CONFIG_NAME = _PACKAGED_CONFIG.name.replace(".example", "", 1)


def ensure_exe_config(
    *,
    executable: Path | None = None,
    runtime_root: Path | None = None,
) -> Path | None:
    """首次启动冻结 EXE 时复制默认配置，源码运行时返回 None。

    测试可显式传入可执行文件和运行时目录；正式运行则从 PyInstaller
    提供的 ``sys.executable`` 与 ``sys._MEIPASS`` 推导路径。目标配置位于
    EXE 同级；目标已经存在时直接复用，绝不覆盖用户修改。
    """

    if executable is None and runtime_root is None:
        if not getattr(sys, "frozen", False):
            return None
        executable = Path(sys.executable)
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root is None:
            raise RuntimeError("冻结运行时缺少 _MEIPASS 配置资源目录。")
        runtime_root = Path(frozen_root)
    elif executable is None or runtime_root is None:
        raise ValueError("测试路径必须同时提供 executable 和 runtime_root。")

    destination = executable.resolve().parent / _EXTERNAL_CONFIG_NAME
    if destination.is_file():
        return destination

    template = runtime_root.resolve() / _PACKAGED_CONFIG
    if not template.is_file():
        raise FileNotFoundError(f"内置配置模板不存在：{template}")

    payload = template.read_bytes()
    try:
        # 使用排他创建避免并发启动覆盖已生成或用户编辑的配置。
        with destination.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        pass
    return destination


__all__ = ["ensure_exe_config"]

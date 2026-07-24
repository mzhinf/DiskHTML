"""跨模块使用的时间、路径和格式化工具。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def utc_now() -> str:
    """返回可长期保存的 UTC ISO 8601 时间。"""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def timestamp_to_utc(value_ns: int) -> str:
    """将文件时间戳纳秒值转换为 UTC ISO 8601 时间。"""

    return datetime.fromtimestamp(value_ns / 1_000_000_000, UTC).isoformat().replace("+00:00", "Z")


def normalized_path_key(relative_path: str) -> str:
    """生成版本 1 的 Windows 默认路径比较键，保留原始路径另存。"""

    return relative_path.replace("\\", "/").casefold()


def relative_display_path(path: Path, root: Path) -> str:
    """返回使用正斜杠的保真相对路径。"""

    return path.relative_to(root).as_posix()


def format_size(size_bytes: int) -> str:
    """以易读单位显示字节数。"""

    units = ("B", "KB", "MB", "GB", "TB", "PB")
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size_bytes} B"

"""Windows 卷信息采集；物理磁盘映射失败时保留原因而不影响扫描。"""

from __future__ import annotations

import ctypes
import os
import shutil
from pathlib import Path
from typing import Any


def collect_volume_info(source: Path) -> dict[str, Any]:
    """采集与源路径对应的卷信息。"""

    anchor = source.anchor or str(source.resolve().anchor)
    usage = shutil.disk_usage(anchor or source)
    result: dict[str, Any] = {
        "drive_letter": anchor.rstrip("\\/") or None,
        "volume_guid": None,
        "volume_label": None,
        "filesystem": None,
        "total_bytes": usage.total,
        "free_bytes": usage.free,
        "disk_model": None,
        "disk_serial": None,
        "partition_json": "[]",
        "capture_error": "物理磁盘型号和序列号采集将在 Windows 适配层完善；当前不参与一致性判断。",
    }
    if os.name != "nt" or not anchor:
        return result
    try:
        label = ctypes.create_unicode_buffer(261)
        filesystem = ctypes.create_unicode_buffer(261)
        serial = ctypes.c_ulong()
        maximum_component = ctypes.c_ulong()
        flags = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            anchor,
            label,
            len(label),
            ctypes.byref(serial),
            ctypes.byref(maximum_component),
            ctypes.byref(flags),
            filesystem,
            len(filesystem),
        )
        if ok:
            result["volume_label"] = label.value or None
            result["filesystem"] = filesystem.value or None
            result["volume_guid"] = f"{serial.value:08X}"
    except OSError as exc:
        result["capture_error"] = f"卷信息采集失败：{exc}"
    return result

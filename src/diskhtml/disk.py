"""Windows 卷、分区和物理磁盘信息采集。"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def collect_volume_info(source: Path) -> dict[str, Any]:
    """采集源路径所在卷的信息；采集缺失原因会随扫描保存。"""

    anchor = source.anchor or str(source.resolve().anchor)
    result: dict[str, Any] = {
        "drive_letter": anchor.rstrip("\\/") or None,
        "volume_guid": None,
        "volume_label": None,
        "filesystem": None,
        "total_bytes": None,
        "free_bytes": None,
        "disk_model": None,
        "disk_serial": None,
        "partition_json": "[]",
        "capture_error": None,
    }
    errors: list[str] = []
    try:
        usage = shutil.disk_usage(anchor or source)
        result["total_bytes"] = usage.total
        result["free_bytes"] = usage.free
    except OSError as exc:
        errors.append(f"容量采集失败：{exc}")

    if os.name != "nt" or not anchor:
        errors.append("当前环境不是可采集 Windows 卷信息的本地卷。")
        result["capture_error"] = "；".join(errors)
        return result

    try:
        _collect_windows_volume_fields(anchor, result)
    except OSError as exc:
        errors.append(f"卷信息采集失败：{exc}")
    try:
        _collect_windows_disk_fields(result)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        errors.append(f"物理磁盘信息采集失败：{exc}")
    result["capture_error"] = "；".join(errors) or None
    return result


def _collect_windows_volume_fields(anchor: str, result: dict[str, Any]) -> None:
    """通过 Win32 API 采集卷标、文件系统、序列号和卷 GUID。"""

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
    if not ok:
        raise ctypes.WinError()
    guid = ctypes.create_unicode_buffer(261)
    if ctypes.windll.kernel32.GetVolumeNameForVolumeMountPointW(anchor, guid, len(guid)):
        result["volume_guid"] = guid.value or None
    else:
        result["volume_guid"] = f"SERIAL-{serial.value:08X}"
    result["volume_label"] = label.value or None
    result["filesystem"] = filesystem.value or None


def _collect_windows_disk_fields(result: dict[str, Any]) -> None:
    """调用内置 PowerShell 获取分区、磁盘型号和序列号。"""

    drive = str(result["drive_letter"] or "")
    if len(drive) != 2 or drive[1] != ":":
        raise ValueError("无法从源路径识别盘符")
    script = (
        "$partition = Get-Partition -DriveLetter '"
        + drive[0].replace("'", "''")
        + "' -ErrorAction Stop; "
        "$disk = $partition | Get-Disk -ErrorAction Stop; "
        "[pscustomobject]@{"
        "model=$disk.FriendlyName;serial=$disk.SerialNumber;"
        "partitions=@($partition | Select-Object DiskNumber,PartitionNumber,DriveLetter,"
        "Offset,Size,Type)} | ConvertTo-Json -Depth 4 -Compress"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    payload = json.loads(completed.stdout)
    result["disk_model"] = payload.get("model") or None
    result["disk_serial"] = payload.get("serial") or None
    partitions = payload.get("partitions") or []
    result["partition_json"] = json.dumps(partitions, ensure_ascii=False, separators=(",", ":"))

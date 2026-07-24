"""领域模型、错误分类与状态机契约。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SourceType(StrEnum):
    """扫描目标类型。"""

    FILE = "FILE"
    DIRECTORY = "DIRECTORY"
    VOLUME = "VOLUME"


class ScanStatus(StrEnum):
    """扫描任务的生命周期状态。"""

    PENDING = "PENDING"
    SCANNING = "SCANNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class HashStatus(StrEnum):
    """单个文件 Hash 的可信状态。"""

    PENDING = "PENDING"
    HASHING = "HASHING"
    OK = "OK"
    UNSTABLE = "UNSTABLE"
    ERROR = "ERROR"


class CompareStatus(StrEnum):
    """比较条目的分类。"""

    MATCH = "MATCH"
    CHANGED = "CHANGED"
    ADDED = "ADDED"
    MISSING = "MISSING"
    ERROR = "ERROR"


class ErrorCode(StrEnum):
    """跨模块稳定使用的错误分类。"""

    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    ENTRY_ERROR = "ENTRY_ERROR"
    READ_ERROR = "READ_ERROR"
    FILE_DISAPPEARED = "FILE_DISAPPEARED"
    CHANGED_DURING_HASH = "CHANGED_DURING_HASH"
    PATH_COLLISION = "PATH_COLLISION"
    DATABASE_ERROR = "DATABASE_ERROR"
    VOLUME_INFO_ERROR = "VOLUME_INFO_ERROR"
    UNKNOWN = "UNKNOWN"


_SCAN_TRANSITIONS: Mapping[ScanStatus, frozenset[ScanStatus]] = {
    ScanStatus.PENDING: frozenset({ScanStatus.SCANNING, ScanStatus.CANCELLED, ScanStatus.FAILED}),
    ScanStatus.SCANNING: frozenset(
        {
            ScanStatus.PAUSED,
            ScanStatus.COMPLETED,
            ScanStatus.CANCELLED,
            ScanStatus.FAILED,
        }
    ),
    ScanStatus.PAUSED: frozenset({ScanStatus.SCANNING, ScanStatus.CANCELLED, ScanStatus.FAILED}),
    # 取消或失败后允许从已完整提交的文件边界恢复。
    ScanStatus.CANCELLED: frozenset({ScanStatus.SCANNING}),
    ScanStatus.FAILED: frozenset({ScanStatus.SCANNING}),
    ScanStatus.COMPLETED: frozenset(),
}


def validate_scan_transition(current: ScanStatus, target: ScanStatus) -> None:
    """校验扫描状态转换，不允许绕过持久化生命周期契约。"""

    if current == target:
        return
    if target not in _SCAN_TRANSITIONS[current]:
        raise ValueError(f"不允许的扫描状态转换：{current} -> {target}")


@dataclass(frozen=True)
class ScanJob:
    """持久化扫描任务的领域视图。"""

    id: str
    source_type: SourceType
    source_path: str
    status: ScanStatus
    hash_algorithm: str
    options: Mapping[str, Any]
    started_at: str
    updated_at: str
    completed_at: str | None = None


@dataclass(frozen=True)
class VolumeInfo:
    """扫描时采集的卷与物理介质信息。"""

    drive_letter: str | None
    volume_guid: str | None
    volume_label: str | None
    filesystem: str | None
    total_bytes: int | None
    free_bytes: int | None
    disk_model: str | None = None
    disk_serial: str | None = None
    capture_error: str | None = None


@dataclass(frozen=True)
class FileRecord:
    """单个文件的元数据、摘要和可信状态。"""

    relative_path: str
    path_key: str
    name: str
    extension: str
    size_bytes: int | None
    modified_time: str | None
    mtime_ns: int | None
    hash_status: HashStatus
    sha256: str | None = None
    sha512: str | None = None
    error_code: ErrorCode | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class CompareResult:
    """按规范化相对路径对齐后的单条比较结果。"""

    relative_path: str
    status: CompareStatus
    old_size_bytes: int | None = None
    new_size_bytes: int | None = None
    old_sha256: str | None = None
    new_sha256: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ErrorRecord:
    """可追踪且不得静默丢弃的错误记录。"""

    code: ErrorCode
    message: str
    relative_path: str | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class ScanProgress:
    """向 CLI 或 GUI 报告的扫描进度快照。"""

    scan_id: str
    files_seen: int
    files_completed: int
    bytes_hashed: int
    current_path: str | None


ProgressCallback = Callable[[ScanProgress], None]

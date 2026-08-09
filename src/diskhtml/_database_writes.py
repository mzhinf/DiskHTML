"""逐条与批量数据库入口共用的 SQL 写入和参数归一化。"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .models import CompareStatus, ScanStatus
from .util import utc_now

_VOLUME_COLUMNS = (
    "drive_letter",
    "volume_guid",
    "volume_label",
    "filesystem",
    "total_bytes",
    "free_bytes",
    "disk_model",
    "disk_serial",
    "partition_json",
    "capture_error",
)
_FILE_COLUMNS = (
    "relative_path",
    "path_key",
    "name",
    "extension",
    "size_bytes",
    "created_time",
    "modified_time",
    "mtime_ns",
    "sha256",
    "sha512",
    "hash_algorithm",
    "hash_status",
    "attempt_count",
    "error_code",
    "error_message",
    "hashed_at",
)


def set_scan_status(
    connection: sqlite3.Connection,
    scan_id: str,
    status: ScanStatus,
    completed: bool = False,
) -> None:
    """更新扫描状态、更新时间和可选完成时间。"""

    now = utc_now()
    connection.execute(
        "UPDATE scan_jobs SET status = ?, updated_at = ?, completed_at = ? WHERE id = ?",
        (status, now, now if completed else None, scan_id),
    )


def update_progress(
    connection: sqlite3.Connection,
    scan_id: str,
    seen: int,
    completed: int,
    bytes_hashed: int,
) -> None:
    """更新扫描的可恢复进度计数。"""

    connection.execute(
        """UPDATE scan_jobs SET files_seen = ?, files_hashed = ?, bytes_hashed = ?,
           updated_at = ? WHERE id = ?""",
        (seen, completed, bytes_hashed, utc_now(), scan_id),
    )


def record_volume(connection: sqlite3.Connection, scan_id: str, values: dict[str, Any]) -> None:
    """用归一化字段替换扫描对应的卷信息。"""

    connection.execute("DELETE FROM volumes WHERE scan_id = ?", (scan_id,))
    connection.execute(
        f"INSERT INTO volumes(scan_id, {', '.join(_VOLUME_COLUMNS)}) "
        f"VALUES (?, {', '.join('?' for _ in _VOLUME_COLUMNS)})",
        (scan_id, *(values.get(column) for column in _VOLUME_COLUMNS)),
    )


def record_directory(
    connection: sqlite3.Connection,
    scan_id: str,
    relative_path: str,
    path_key: str,
    parent_path_key: str | None,
    error: str | None = None,
    created_time: str | None = None,
    modified_time: str | None = None,
) -> None:
    """插入或更新目录记录及其时间和扫描状态。"""

    connection.execute(
        """INSERT INTO directories(
               scan_id, relative_path, path_key, parent_path_key, created_time, modified_time,
               scan_status, error_message
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(scan_id, path_key) DO UPDATE SET
               created_time = excluded.created_time,
               modified_time = excluded.modified_time,
               scan_status = excluded.scan_status,
               error_message = excluded.error_message""",
        (
            scan_id,
            relative_path,
            path_key,
            parent_path_key,
            created_time,
            modified_time,
            "ERROR" if error else "OK",
            error,
        ),
    )


def record_error(
    connection: sqlite3.Connection,
    scan_id: str,
    relative_path: str | None,
    code: str,
    message: str,
) -> None:
    """写入带创建时间的可追踪扫描错误。"""

    connection.execute(
        """INSERT INTO scan_errors(
               scan_id, relative_path, error_code, error_message, created_at
           ) VALUES (?, ?, ?, ?, ?)""",
        (scan_id, relative_path, code, message, utc_now()),
    )


def record_file(connection: sqlite3.Connection, scan_id: str, item: dict[str, Any]) -> None:
    """按稳定列顺序插入或更新文件 Hash 结果。"""

    values = [item.get(column) for column in _FILE_COLUMNS]
    assignments = ", ".join(
        f"{column} = excluded.{column}"
        for column in _FILE_COLUMNS
        if column not in {"relative_path", "path_key"}
    )
    connection.execute(
        f"""INSERT INTO files(scan_id, {", ".join(_FILE_COLUMNS)})
            VALUES (?, {", ".join("?" for _ in _FILE_COLUMNS)})
            ON CONFLICT(scan_id, path_key) DO UPDATE SET {assignments}""",
        (scan_id, *values),
    )


def set_compare_status(
    connection: sqlite3.Connection,
    compare_id: str,
    status: str,
    summary: dict[str, int] | None = None,
    completed: bool = False,
) -> None:
    """更新比较状态、稳定摘要和可选完成时间。"""

    connection.execute(
        """UPDATE compare_jobs
           SET status = ?, summary_json = ?, completed_at = ?
           WHERE id = ?""",
        (
            status,
            json.dumps(summary or {}, ensure_ascii=False, sort_keys=True),
            utc_now() if completed else None,
            compare_id,
        ),
    )


def record_compare_entry(
    connection: sqlite3.Connection, compare_id: str, item: dict[str, Any]
) -> None:
    """归一化比较状态并写入一条比较结果。"""

    status = CompareStatus(item["status"])
    connection.execute(
        """INSERT INTO compare_entries(
               compare_id, relative_path, status, old_size_bytes, new_size_bytes,
               old_sha256, new_sha256, old_hash_algorithm, new_hash_algorithm,
               error_message
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            compare_id,
            item["relative_path"],
            status,
            item.get("old_size_bytes"),
            item.get("new_size_bytes"),
            item.get("old_sha256"),
            item.get("new_sha256"),
            item.get("old_hash_algorithm"),
            item.get("new_hash_algorithm"),
            item.get("error_message"),
        ),
    )

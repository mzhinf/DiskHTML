"""历史扫描快照的流式比较服务。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .config import ScanConfig
from .database import Database
from .models import CompareStatus
from .scanner import Scanner

_COMPARE_BATCH_SIZE = 1_000


def compare_source_to_scan(
    database: Database,
    source: str,
    historical_scan_id: str,
    options: ScanConfig | None = None,
) -> str:
    """扫描当前文件或目录，并与一个历史扫描快照比较。"""

    current_scan_id = Scanner(database).start(source, options or ScanConfig())
    return compare_scans(database, historical_scan_id, current_scan_id)


def compare_sources(
    database: Database,
    left_source: str,
    right_source: str,
    options: ScanConfig | None = None,
) -> str:
    """扫描两个当前文件或目录，并按左旧右新的方向比较。"""

    scan_options = options or ScanConfig()
    left_scan_id = Scanner(database).start(left_source, scan_options)
    right_scan_id = Scanner(database).start(right_source, scan_options)
    return compare_scans(database, left_scan_id, right_scan_id)


def compare_scans(database: Database, left_scan_id: str, right_scan_id: str) -> str:
    """比较两个已完成扫描，并把流式结果持久化为比较任务。"""

    _require_completed_scan(database, left_scan_id)
    _require_completed_scan(database, right_scan_id)
    compare_id = database.create_compare(f"scan:{left_scan_id}", f"scan:{right_scan_id}")
    database.set_compare_status(compare_id, "RUNNING")
    summary = {status.value: 0 for status in CompareStatus}
    entries: list[dict[str, Any]] = []

    try:
        for entry in _iter_entries(
            database.iter_files(left_scan_id), database.iter_files(right_scan_id)
        ):
            summary[entry["status"].value] += 1
            entries.append(entry)
            if len(entries) >= _COMPARE_BATCH_SIZE:
                _write_entries(database, compare_id, entries)

        with database.batch() as batch:
            for entry in entries:
                batch.record_compare_entry(compare_id, entry)
            batch.set_compare_status(compare_id, "COMPLETED", summary, completed=True)
    except BaseException:
        database.set_compare_status(compare_id, "FAILED", summary)
        raise
    return compare_id


def _require_completed_scan(database: Database, scan_id: str) -> None:
    """拒绝不存在或尚未冻结的扫描快照。"""

    scan = database.get_scan(scan_id)
    if scan is None:
        raise ValueError(f"未找到扫描任务：{scan_id}")
    if scan["status"] != "COMPLETED":
        raise ValueError(f"只能比较已完成的扫描任务：{scan_id}")


def _write_entries(database: Database, compare_id: str, entries: list[dict[str, Any]]) -> None:
    """以有界事务写入当前一批比较结果。"""

    with database.batch() as batch:
        for entry in entries:
            batch.record_compare_entry(compare_id, entry)
    entries.clear()


def _iter_entries(left_rows: Iterator[Any], right_rows: Iterator[Any]) -> Iterator[dict[str, Any]]:
    """按路径比较键归并两个有序文件流。"""

    left = next(left_rows, None)
    right = next(right_rows, None)
    while left is not None or right is not None:
        if right is None or (left is not None and str(left["path_key"]) < str(right["path_key"])):
            yield _one_sided_entry(left, CompareStatus.MISSING, "左侧")
            left = next(left_rows, None)
        elif left is None or str(right["path_key"]) < str(left["path_key"]):
            yield _one_sided_entry(right, CompareStatus.ADDED, "右侧")
            right = next(right_rows, None)
        else:
            yield _both_sides_entry(left, right)
            left = next(left_rows, None)
            right = next(right_rows, None)


def _one_sided_entry(row: Any, status: CompareStatus, side: str) -> dict[str, Any]:
    """为仅存在于一侧的文件构造比较条目。"""

    values: dict[str, Any] = {
        "relative_path": row["relative_path"],
        "status": status,
        "error_message": None,
    }
    if side == "左侧":
        values.update(old_size_bytes=row["size_bytes"], old_sha256=row["sha256"])
    else:
        values.update(new_size_bytes=row["size_bytes"], new_sha256=row["sha256"])
    return values


def _both_sides_entry(left: Any, right: Any) -> dict[str, Any]:
    """以可信 SHA256 为最终依据，构造同路径的比较条目。"""

    trusted = (
        left["hash_status"] == "OK"
        and right["hash_status"] == "OK"
        and left["sha256"] is not None
        and right["sha256"] is not None
    )
    if not trusted:
        status = CompareStatus.ERROR
        message = _untrusted_message(left, right)
    elif left["sha256"] == right["sha256"]:
        status = CompareStatus.MATCH
        message = None
    else:
        status = CompareStatus.CHANGED
        message = None
    return {
        "relative_path": right["relative_path"],
        "status": status,
        "old_size_bytes": left["size_bytes"],
        "new_size_bytes": right["size_bytes"],
        "old_sha256": left["sha256"],
        "new_sha256": right["sha256"],
        "error_message": message,
    }


def _untrusted_message(left: Any, right: Any) -> str:
    """说明哪一侧缺少可用于一致性判断的摘要。"""

    messages = []
    for side, row in (("左侧", left), ("右侧", right)):
        if row["hash_status"] != "OK" or row["sha256"] is None:
            messages.append(f"{side}文件摘要状态为 {row['hash_status']}")
    return "；".join(messages)

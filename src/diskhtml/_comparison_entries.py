"""从两个已排序文件行流生成比较条目的领域内部接口。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .models import CompareStatus
from .sampled_hash import FULL_SHA256_ALGORITHM

__all__ = ("iter_comparison_entries",)


def iter_comparison_entries(
    left_rows: Iterator[Any], right_rows: Iterator[Any]
) -> Iterator[dict[str, Any]]:
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
        values.update(
            old_size_bytes=row["size_bytes"],
            old_sha256=row["sha256"],
            old_hash_algorithm=row["hash_algorithm"],
            old_created_time=row["created_time"],
            old_modified_time=row["modified_time"],
        )
    else:
        values.update(
            new_size_bytes=row["size_bytes"],
            new_sha256=row["sha256"],
            new_hash_algorithm=row["hash_algorithm"],
            new_created_time=row["created_time"],
            new_modified_time=row["modified_time"],
        )
    return values


def _both_sides_entry(left: Any, right: Any) -> dict[str, Any]:
    """按文件大小、实际算法和可信摘要构造同路径比较条目。"""

    trusted = (
        left["hash_status"] == "OK"
        and right["hash_status"] == "OK"
        and left["sha256"] is not None
        and right["sha256"] is not None
        and left["hash_algorithm"] is not None
        and right["hash_algorithm"] is not None
    )
    if not trusted:
        status = CompareStatus.ERROR
        message = _untrusted_message(left, right)
    elif (
        left["size_bytes"] != right["size_bytes"]
        or left["hash_algorithm"] != right["hash_algorithm"]
        or left["sha256"] != right["sha256"]
    ):
        status = CompareStatus.CHANGED
        message = None
    elif left["hash_algorithm"] == FULL_SHA256_ALGORITHM:
        status = CompareStatus.MATCH
        message = None
    else:
        status = CompareStatus.PRECHECK_MATCH
        message = None
    return {
        "relative_path": right["relative_path"],
        "status": status,
        "old_size_bytes": left["size_bytes"],
        "new_size_bytes": right["size_bytes"],
        "old_sha256": left["sha256"],
        "new_sha256": right["sha256"],
        "old_hash_algorithm": left["hash_algorithm"],
        "new_hash_algorithm": right["hash_algorithm"],
        "old_created_time": left["created_time"],
        "new_created_time": right["created_time"],
        "old_modified_time": left["modified_time"],
        "new_modified_time": right["modified_time"],
        "error_message": message,
    }


def _untrusted_message(left: Any, right: Any) -> str:
    """说明哪一侧缺少可用于一致性判断的摘要。"""

    messages = []
    for side, row in (("左侧", left), ("右侧", right)):
        if row["hash_status"] != "OK" or row["sha256"] is None:
            messages.append(f"{side}文件摘要状态为 {row['hash_status']}")
    return "；".join(messages)

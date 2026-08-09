"""SQLite 项目自检的命名规则与稳定问题顺序。"""

from __future__ import annotations

import sqlite3

from ._database_schema import SCHEMA_VERSION
from .models import CompareStatus, HashStatus, ScanStatus, SourceType

_COMPARE_JOB_STATUSES = ("PENDING", "RUNNING", "COMPLETED", "FAILED")


def check_project(
    connection: sqlite3.Connection,
    *,
    integrity: str,
    schema_version: int,
    migration_versions: tuple[int, ...],
) -> tuple[str, ...]:
    """按兼容顺序执行完整性、版本、枚举、引用和计数检查。"""

    problems: list[str] = []
    problems.extend(_integrity_problems(integrity))
    problems.extend(_schema_problems(schema_version, migration_versions))
    problems.extend(_enum_problems(connection))
    problems.extend(_orphan_problems(connection))
    problems.extend(_counter_problems(connection))
    return tuple(problems)


def _integrity_problems(integrity: str) -> tuple[str, ...]:
    """把 SQLite 完整性结果转换为项目问题。"""

    if integrity == "ok":
        return ()
    return (f"SQLite 完整性检查失败：{integrity}",)


def _schema_problems(schema_version: int, migration_versions: tuple[int, ...]) -> tuple[str, ...]:
    """检查模式版本和迁移历史是否与当前契约一致。"""

    problems: list[str] = []
    if schema_version != SCHEMA_VERSION:
        problems.append(f"模式版本不匹配：当前为 {schema_version}，预期为 {SCHEMA_VERSION}")
    expected_migrations = tuple(range(2, SCHEMA_VERSION + 1))
    if migration_versions != expected_migrations:
        problems.append(
            f"迁移记录不匹配：当前为 {migration_versions}，预期为 {expected_migrations}"
        )
    return tuple(problems)


def _enum_problems(connection: sqlite3.Connection) -> tuple[str, ...]:
    """按既定表顺序检查未知枚举值。"""

    enum_checks = (
        (
            "scan_jobs.source_type",
            "source_type",
            "scan_jobs",
            tuple(item.value for item in SourceType),
        ),
        ("scan_jobs.status", "status", "scan_jobs", tuple(item.value for item in ScanStatus)),
        ("files.hash_status", "hash_status", "files", tuple(item.value for item in HashStatus)),
        ("compare_jobs.status", "status", "compare_jobs", _COMPARE_JOB_STATUSES),
        (
            "compare_entries.status",
            "status",
            "compare_entries",
            tuple(item.value for item in CompareStatus),
        ),
    )
    problems: list[str] = []
    for label, column, table, values in enum_checks:
        placeholders = ", ".join("?" for _ in values)
        count = connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {column} NOT IN ({placeholders})", values
        ).fetchone()[0]
        if count:
            problems.append(f"{label} 存在 {count} 条未知枚举值")
    return tuple(problems)


def _orphan_problems(connection: sqlite3.Connection) -> tuple[str, ...]:
    """按既定子表顺序检查孤立记录。"""

    orphan_checks = (
        ("volumes", "scan_id", "scan_jobs"),
        ("directories", "scan_id", "scan_jobs"),
        ("files", "scan_id", "scan_jobs"),
        ("scan_errors", "scan_id", "scan_jobs"),
        ("compare_entries", "compare_id", "compare_jobs"),
    )
    problems: list[str] = []
    for table, foreign_key, parent_table in orphan_checks:
        count = connection.execute(
            f"""SELECT COUNT(*) FROM {table} AS child
                LEFT JOIN {parent_table} AS parent ON parent.id = child.{foreign_key}
                WHERE parent.id IS NULL"""
        ).fetchone()[0]
        if count:
            problems.append(f"{table} 存在 {count} 条孤立记录")
    return tuple(problems)


def _counter_problems(connection: sqlite3.Connection) -> tuple[str, ...]:
    """检查扫描进度计数是否可由文件记录重建。"""

    rows = connection.execute(
        """SELECT job.id
           FROM scan_jobs AS job
           WHERE job.files_hashed != (
               SELECT COUNT(*) FROM files WHERE scan_id = job.id
           )
              OR job.bytes_hashed != (
               SELECT COALESCE(SUM(CASE WHEN hash_status = 'OK' THEN size_bytes ELSE 0 END), 0)
               FROM files WHERE scan_id = job.id
           )"""
    ).fetchall()
    if not rows:
        return ()
    return (f"{len(rows)} 个扫描任务的进度计数与文件记录不一致",)

"""SQLite 数据库、迁移、批量事务与流式仓储接口。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from threading import RLock
from typing import Any

from . import _database_writes as writes
from ._database_schema import (
    CREATE_SCHEMA_META,
    MIGRATIONS,
    SCHEMA_VERSION,
    store_schema_version,
    stored_schema_version,
    validate_schema,
)
from ._project_check import check_project
from .models import ScanStatus, validate_scan_transition
from .sampled_hash import FULL_SHA256_ALGORITHM
from .util import utc_now


class Database:
    """封装单个项目数据库；调用方应让一个编排线程承担写入。"""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        try:
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA journal_mode = WAL")
            self.connection.execute("PRAGMA synchronous = NORMAL")
            self.migrate()
        except BaseException:
            self.connection.close()
            raise

    @classmethod
    def open_existing(cls, path: Path | str) -> Database:
        """打开并迁移已有项目数据库；不存在的路径会被明确拒绝。"""

        database_path = Path(path)
        if not database_path.is_file():
            raise FileNotFoundError(f"项目数据库不存在：{database_path}")
        return cls(database_path)

    def __enter__(self) -> Database:
        """允许使用上下文管理器自动关闭连接。"""

        return self

    def __exit__(self, *_args: object) -> None:
        """退出上下文时关闭连接。"""

        self.close()

    def close(self) -> None:
        """关闭数据库连接。"""

        self.connection.close()

    def migrate(self) -> None:
        """按顺序且在单一事务中执行版本化迁移。"""

        with self._transaction() as connection:
            connection.execute(CREATE_SCHEMA_META)
            current_version = stored_schema_version(connection)
            if current_version not in {0, SCHEMA_VERSION}:
                raise RuntimeError(
                    f"数据库模式版本 {current_version} 与当前版本 {SCHEMA_VERSION} 不兼容，请重新生成"
                )
            for version in range(current_version + 1, SCHEMA_VERSION + 1):
                for statement in MIGRATIONS[version]:
                    connection.execute(statement)
                store_schema_version(connection, version)
                if version >= 2:
                    connection.execute(
                        "INSERT OR REPLACE INTO migration_history(version, applied_at) VALUES (?, ?)",
                        (version, utc_now()),
                    )
            validate_schema(connection)

    def schema_version(self) -> int:
        """返回已打开数据库的模式版本。"""

        return stored_schema_version(self.connection)

    def migration_versions(self) -> tuple[int, ...]:
        """返回已记录的迁移版本，供诊断与导入校验使用。"""

        rows = self.connection.execute("SELECT version FROM migration_history ORDER BY version")
        return tuple(int(row["version"]) for row in rows)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """开启立即写事务，失败时确保整批修改回滚。"""

        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
            except BaseException:
                self.connection.rollback()
                raise
            else:
                self.connection.commit()

    @contextmanager
    def batch(self) -> Iterator[DatabaseBatch]:
        """提供单事务批量写入器，避免逐文件提交。"""

        writer = DatabaseBatch(self)
        with writer:
            yield writer

    def create_scan(
        self,
        source_type: str,
        source_path: str,
        options: dict[str, Any],
        hash_algorithm: str = FULL_SHA256_ALGORITHM,
    ) -> str:
        """创建等待执行的扫描任务。"""

        scan_id = str(uuid.uuid4())
        now = utc_now()
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO scan_jobs(
                    id, source_type, source_path, status, hash_algorithm, options_json,
                    started_at, updated_at, format_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scan_id,
                    source_type,
                    source_path,
                    ScanStatus.PENDING,
                    hash_algorithm,
                    json.dumps(options, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                    str(SCHEMA_VERSION),
                ),
            )
        return scan_id

    def get_scan(self, scan_id: str) -> sqlite3.Row | None:
        """取得一个扫描任务。"""

        with self._lock:
            return self.connection.execute(
                "SELECT * FROM scan_jobs WHERE id = ?", (scan_id,)
            ).fetchone()

    def iter_scans(self) -> Iterator[sqlite3.Row]:
        """按创建时间流式遍历扫描任务。"""

        with self._lock:
            yield from self.connection.execute("SELECT * FROM scan_jobs ORDER BY started_at, id")

    def latest_scan(self) -> sqlite3.Row | None:
        """取得最近完成的扫描任务。"""

        return self.connection.execute(
            "SELECT * FROM scan_jobs WHERE status = ? ORDER BY completed_at DESC LIMIT 1",
            (ScanStatus.COMPLETED,),
        ).fetchone()

    def set_scan_status(self, scan_id: str, status: ScanStatus, completed: bool = False) -> None:
        """更新扫描状态与更新时间。"""

        row = self.get_scan(scan_id)
        if row is None:
            raise ValueError(f"未找到扫描任务：{scan_id}")
        validate_scan_transition(ScanStatus(row["status"]), status)
        with self._transaction() as connection:
            writes.set_scan_status(connection, scan_id, status, completed)

    def update_progress(self, scan_id: str, seen: int, completed: int, bytes_hashed: int) -> None:
        """保存可恢复的进度计数。"""

        with self._transaction() as connection:
            writes.update_progress(connection, scan_id, seen, completed, bytes_hashed)

    def record_volume(self, scan_id: str, values: dict[str, Any]) -> None:
        """记录扫描时采集到的卷信息。"""

        with self._transaction() as connection:
            writes.record_volume(connection, scan_id, values)

    def record_directory(
        self,
        scan_id: str,
        relative_path: str,
        path_key: str,
        parent_path_key: str | None,
        error: str | None = None,
        created_time: str | None = None,
        modified_time: str | None = None,
    ) -> None:
        """插入或更新一个目录记录及其时间元数据。"""

        with self._transaction() as connection:
            writes.record_directory(
                connection,
                scan_id,
                relative_path,
                path_key,
                parent_path_key,
                error,
                created_time,
                modified_time,
            )

    def record_error(
        self, scan_id: str, relative_path: str | None, code: str, message: str
    ) -> None:
        """保留不可忽略的扫描错误。"""

        with self._transaction() as connection:
            writes.record_error(connection, scan_id, relative_path, code, message)

    def get_file(self, scan_id: str, path_key: str) -> sqlite3.Row | None:
        """按比较键取得已有文件记录，用于恢复时跳过稳定结果。"""

        return self.connection.execute(
            "SELECT * FROM files WHERE scan_id = ? AND path_key = ?", (scan_id, path_key)
        ).fetchone()

    def record_file(self, scan_id: str, item: dict[str, Any]) -> None:
        """以独立事务插入或更新一个文件记录。批量调用应改用 batch。"""

        with self._transaction() as connection:
            writes.record_file(connection, scan_id, item)

    def iter_files(self, scan_id: str) -> Iterator[sqlite3.Row]:
        """按路径比较键流式遍历文件。"""

        yield from self.connection.execute(
            "SELECT * FROM files WHERE scan_id = ? ORDER BY path_key", (scan_id,)
        )

    def iter_directories(self, scan_id: str) -> Iterator[sqlite3.Row]:
        """按路径比较键流式遍历目录。"""

        yield from self.connection.execute(
            "SELECT * FROM directories WHERE scan_id = ? ORDER BY path_key", (scan_id,)
        )

    def iter_errors(self, scan_id: str) -> Iterator[sqlite3.Row]:
        """按写入顺序流式遍历扫描错误。"""

        yield from self.connection.execute(
            "SELECT * FROM scan_errors WHERE scan_id = ? ORDER BY id", (scan_id,)
        )

    def summary(self, scan_id: str) -> dict[str, int]:
        """返回扫描统计，不把文件记录加载到内存。"""

        row = self.connection.execute(
            """SELECT COUNT(*) AS total_files,
                      COALESCE(SUM(CASE WHEN hash_status = 'OK' THEN size_bytes ELSE 0 END), 0) AS total_size,
                      COALESCE(SUM(CASE WHEN hash_status = 'OK' THEN 1 ELSE 0 END), 0) AS hashed_files,
                      COALESCE(SUM(CASE WHEN hash_status IN ('ERROR', 'UNSTABLE') THEN 1 ELSE 0 END), 0) AS problem_files
               FROM files WHERE scan_id = ?""",
            (scan_id,),
        ).fetchone()
        directory_count = self.connection.execute(
            "SELECT COUNT(*) FROM directories WHERE scan_id = ?", (scan_id,)
        ).fetchone()[0]
        return {**dict(row), "total_directories": directory_count}

    def get_volume(self, scan_id: str) -> sqlite3.Row | None:
        """取得一个扫描任务的卷信息。"""

        return self.connection.execute(
            "SELECT * FROM volumes WHERE scan_id = ?", (scan_id,)
        ).fetchone()

    def create_compare(self, left_source: str, right_source: str) -> str:
        """创建等待执行的比较任务。"""

        compare_id = str(uuid.uuid4())
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO compare_jobs(id, left_source, right_source, status, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (compare_id, left_source, right_source, "PENDING", utc_now()),
            )
        return compare_id

    def get_compare(self, compare_id: str) -> sqlite3.Row | None:
        """取得一个比较任务。"""

        return self.connection.execute(
            "SELECT * FROM compare_jobs WHERE id = ?", (compare_id,)
        ).fetchone()

    def set_compare_status(
        self,
        compare_id: str,
        status: str,
        summary: dict[str, int] | None = None,
        completed: bool = False,
    ) -> None:
        """更新比较任务状态与可重建的统计摘要。"""

        if self.get_compare(compare_id) is None:
            raise ValueError(f"未找到比较任务：{compare_id}")
        with self._transaction() as connection:
            writes.set_compare_status(connection, compare_id, status, summary, completed)

    def record_compare_entry(self, compare_id: str, item: dict[str, Any]) -> None:
        """以独立事务写入一条比较结果。批量调用应改用 batch。"""

        with self._transaction() as connection:
            writes.record_compare_entry(connection, compare_id, item)

    def iter_compare_entries(self, compare_id: str) -> Iterator[sqlite3.Row]:
        """按路径流式遍历比较结果。"""

        yield from self.connection.execute(
            "SELECT * FROM compare_entries WHERE compare_id = ? ORDER BY relative_path, id",
            (compare_id,),
        )

    def integrity_check(self) -> str:
        """执行 SQLite 自检。"""

        return self.connection.execute("PRAGMA integrity_check").fetchone()[0]

    def project_check(self) -> tuple[str, ...]:
        """校验项目模式、引用关系、枚举值与扫描进度计数，返回全部发现的问题。"""

        return check_project(
            self.connection,
            integrity=self.integrity_check(),
            schema_version=self.schema_version(),
            migration_versions=self.migration_versions(),
        )


class DatabaseBatch(AbstractContextManager["DatabaseBatch"]):
    """一次只由一个编排线程持有的 SQLite 批量写入事务。"""

    def __init__(self, database: Database):
        self._database = database
        self._connection = database.connection
        self._active = False

    def __enter__(self) -> DatabaseBatch:
        """开始立即写事务，确保批次中的记录原子可见。"""

        self._database._lock.acquire()
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except BaseException:
            self._database._lock.release()
            raise
        self._active = True
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        """正常退出提交，异常退出回滚整个批次。"""

        try:
            if exc_type is None:
                self._connection.commit()
            else:
                self._connection.rollback()
        finally:
            self._active = False
            self._database._lock.release()
        return False

    def set_scan_status(self, scan_id: str, status: ScanStatus, completed: bool = False) -> None:
        """在当前批次内更新扫描状态。"""

        self._require_active()
        writes.set_scan_status(self._connection, scan_id, status, completed)

    def update_progress(self, scan_id: str, seen: int, completed: int, bytes_hashed: int) -> None:
        """在当前批次内更新可恢复进度。"""

        self._require_active()
        writes.update_progress(self._connection, scan_id, seen, completed, bytes_hashed)

    def record_volume(self, scan_id: str, values: dict[str, Any]) -> None:
        """在当前批次内替换扫描对应的卷信息。"""

        self._require_active()
        writes.record_volume(self._connection, scan_id, values)

    def record_directory(
        self,
        scan_id: str,
        relative_path: str,
        path_key: str,
        parent_path_key: str | None,
        error: str | None = None,
        created_time: str | None = None,
        modified_time: str | None = None,
    ) -> None:
        """在当前批次内插入或更新目录记录及其时间元数据。"""

        self._require_active()
        writes.record_directory(
            self._connection,
            scan_id,
            relative_path,
            path_key,
            parent_path_key,
            error,
            created_time,
            modified_time,
        )

    def record_error(
        self, scan_id: str, relative_path: str | None, code: str, message: str
    ) -> None:
        """在当前批次内写入可追踪错误。"""

        self._require_active()
        writes.record_error(self._connection, scan_id, relative_path, code, message)

    def record_file(self, scan_id: str, item: dict[str, Any]) -> None:
        """在当前批次内插入或更新文件 Hash 结果。"""

        self._require_active()
        writes.record_file(self._connection, scan_id, item)

    def set_compare_status(
        self,
        compare_id: str,
        status: str,
        summary: dict[str, int] | None = None,
        completed: bool = False,
    ) -> None:
        """在当前批次内更新比较状态和摘要。"""

        self._require_active()
        writes.set_compare_status(self._connection, compare_id, status, summary, completed)

    def record_compare_entry(self, compare_id: str, item: dict[str, Any]) -> None:
        """在当前批次内写入一条比较结果。"""

        self._require_active()
        writes.record_compare_entry(self._connection, compare_id, item)

    def _require_active(self) -> None:
        if not self._active:
            raise RuntimeError("批量写入器尚未开启或已经关闭")

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

from .models import CompareStatus, HashStatus, ScanStatus, SourceType, validate_scan_transition
from .util import utc_now

SCHEMA_VERSION = 2

_CREATE_SCHEMA_META = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

_MIGRATION_1 = (
    """
    CREATE TABLE IF NOT EXISTS volumes (
        id INTEGER PRIMARY KEY,
        scan_id TEXT NOT NULL,
        drive_letter TEXT,
        volume_guid TEXT,
        volume_label TEXT,
        filesystem TEXT,
        total_bytes INTEGER,
        free_bytes INTEGER,
        disk_model TEXT,
        disk_serial TEXT,
        partition_json TEXT NOT NULL DEFAULT '[]',
        capture_error TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scan_jobs (
        id TEXT PRIMARY KEY,
        source_type TEXT NOT NULL,
        source_path TEXT NOT NULL,
        status TEXT NOT NULL,
        hash_algorithm TEXT NOT NULL,
        options_json TEXT NOT NULL,
        started_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT,
        files_seen INTEGER NOT NULL DEFAULT 0,
        files_hashed INTEGER NOT NULL DEFAULT 0,
        bytes_hashed INTEGER NOT NULL DEFAULT 0,
        format_version TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS directories (
        id INTEGER PRIMARY KEY,
        scan_id TEXT NOT NULL,
        relative_path TEXT NOT NULL,
        path_key TEXT NOT NULL,
        parent_path_key TEXT,
        scan_status TEXT NOT NULL DEFAULT 'OK',
        error_message TEXT,
        UNIQUE(scan_id, path_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY,
        scan_id TEXT NOT NULL,
        relative_path TEXT NOT NULL,
        path_key TEXT NOT NULL,
        name TEXT NOT NULL,
        extension TEXT NOT NULL,
        size_bytes INTEGER,
        created_time TEXT,
        modified_time TEXT,
        mtime_ns INTEGER,
        sha256 TEXT,
        sha512 TEXT,
        hash_status TEXT NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        error_code TEXT,
        error_message TEXT,
        hashed_at TEXT,
        UNIQUE(scan_id, path_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scan_errors (
        id INTEGER PRIMARY KEY,
        scan_id TEXT NOT NULL,
        relative_path TEXT,
        error_code TEXT NOT NULL,
        error_message TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS compare_jobs (
        id TEXT PRIMARY KEY,
        left_source TEXT NOT NULL,
        right_source TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        completed_at TEXT,
        summary_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS compare_entries (
        id INTEGER PRIMARY KEY,
        compare_id TEXT NOT NULL,
        relative_path TEXT NOT NULL,
        status TEXT NOT NULL,
        old_size_bytes INTEGER,
        new_size_bytes INTEGER,
        old_sha256 TEXT,
        new_sha256 TEXT,
        error_message TEXT
    )
    """,
)

_MIGRATION_2 = (
    """
    CREATE TABLE IF NOT EXISTS migration_history (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_files_scan_status ON files(scan_id, hash_status)",
    "CREATE INDEX IF NOT EXISTS idx_files_scan_path ON files(scan_id, path_key, size_bytes, sha256)",
    "CREATE INDEX IF NOT EXISTS idx_directories_scan_parent ON directories(scan_id, parent_path_key)",
    "CREATE INDEX IF NOT EXISTS idx_errors_scan_path ON scan_errors(scan_id, relative_path)",
    "CREATE INDEX IF NOT EXISTS idx_compare_entries_job ON compare_entries(compare_id, status, relative_path)",
)

MIGRATIONS: dict[int, tuple[str, ...]] = {1: _MIGRATION_1, 2: _MIGRATION_2}
_REQUIRED_TABLES = frozenset(
    {
        "schema_meta",
        "migration_history",
        "volumes",
        "scan_jobs",
        "directories",
        "files",
        "scan_errors",
        "compare_jobs",
        "compare_entries",
    }
)


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
            connection.execute(_CREATE_SCHEMA_META)
            current_version = self._stored_schema_version(connection)
            if current_version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"数据库模式版本 {current_version} 新于当前程序支持的版本 {SCHEMA_VERSION}"
                )
            for version in range(current_version + 1, SCHEMA_VERSION + 1):
                for statement in MIGRATIONS[version]:
                    connection.execute(statement)
                self._store_schema_version(connection, version)
                if version >= 2:
                    connection.execute(
                        "INSERT OR REPLACE INTO migration_history(version, applied_at) VALUES (?, ?)",
                        (version, utc_now()),
                    )
            self._validate_schema(connection)

    def schema_version(self) -> int:
        """返回已打开数据库的模式版本。"""

        return self._stored_schema_version(self.connection)

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

    def create_scan(self, source_type: str, source_path: str, options: dict[str, Any]) -> str:
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
                    "SHA256" + ("+SHA512" if options.get("sha512") else ""),
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
        with self.batch() as batch:
            batch.set_scan_status(scan_id, status, completed)

    def update_progress(self, scan_id: str, seen: int, completed: int, bytes_hashed: int) -> None:
        """保存可恢复的进度计数。"""

        with self.batch() as batch:
            batch.update_progress(scan_id, seen, completed, bytes_hashed)

    def record_volume(self, scan_id: str, values: dict[str, Any]) -> None:
        """记录扫描时采集到的卷信息。"""

        with self.batch() as batch:
            batch.record_volume(scan_id, values)

    def record_directory(
        self,
        scan_id: str,
        relative_path: str,
        path_key: str,
        parent_path_key: str | None,
        error: str | None = None,
    ) -> None:
        """插入或更新一个目录记录。"""

        with self.batch() as batch:
            batch.record_directory(scan_id, relative_path, path_key, parent_path_key, error)

    def record_error(
        self, scan_id: str, relative_path: str | None, code: str, message: str
    ) -> None:
        """保留不可忽略的扫描错误。"""

        with self.batch() as batch:
            batch.record_error(scan_id, relative_path, code, message)

    def get_file(self, scan_id: str, path_key: str) -> sqlite3.Row | None:
        """按比较键取得已有文件记录，用于恢复时跳过稳定结果。"""

        return self.connection.execute(
            "SELECT * FROM files WHERE scan_id = ? AND path_key = ?", (scan_id, path_key)
        ).fetchone()

    def record_file(self, scan_id: str, item: dict[str, Any]) -> None:
        """以独立事务插入或更新一个文件记录。批量调用应改用 batch。"""

        with self.batch() as batch:
            batch.record_file(scan_id, item)

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
        with self.batch() as batch:
            batch.set_compare_status(compare_id, status, summary, completed)

    def record_compare_entry(self, compare_id: str, item: dict[str, Any]) -> None:
        """以独立事务写入一条比较结果。批量调用应改用 batch。"""

        with self.batch() as batch:
            batch.record_compare_entry(compare_id, item)

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

        problems: list[str] = []
        integrity = self.integrity_check()
        if integrity != "ok":
            problems.append(f"SQLite 完整性检查失败：{integrity}")
        if self.schema_version() != SCHEMA_VERSION:
            problems.append(
                f"模式版本不匹配：当前为 {self.schema_version()}，预期为 {SCHEMA_VERSION}"
            )
        expected_migrations = tuple(range(2, SCHEMA_VERSION + 1))
        if self.migration_versions() != expected_migrations:
            problems.append(
                f"迁移记录不匹配：当前为 {self.migration_versions()}，预期为 {expected_migrations}"
            )

        allowed_sources = tuple(item.value for item in SourceType)
        allowed_scan_statuses = tuple(item.value for item in ScanStatus)
        allowed_hash_statuses = tuple(item.value for item in HashStatus)
        allowed_compare_statuses = ("PENDING", "RUNNING", "COMPLETED", "FAILED")
        enum_checks = (
            ("scan_jobs.source_type", "source_type", "scan_jobs", allowed_sources),
            ("scan_jobs.status", "status", "scan_jobs", allowed_scan_statuses),
            ("files.hash_status", "hash_status", "files", allowed_hash_statuses),
            ("compare_jobs.status", "status", "compare_jobs", allowed_compare_statuses),
            (
                "compare_entries.status",
                "status",
                "compare_entries",
                tuple(item.value for item in CompareStatus),
            ),
        )
        for label, column, table, values in enum_checks:
            placeholders = ", ".join("?" for _ in values)
            count = self.connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column} NOT IN ({placeholders})", values
            ).fetchone()[0]
            if count:
                problems.append(f"{label} 存在 {count} 条未知枚举值")

        orphan_checks = (
            ("volumes", "scan_id", "scan_jobs"),
            ("directories", "scan_id", "scan_jobs"),
            ("files", "scan_id", "scan_jobs"),
            ("scan_errors", "scan_id", "scan_jobs"),
            ("compare_entries", "compare_id", "compare_jobs"),
        )
        for table, foreign_key, parent_table in orphan_checks:
            count = self.connection.execute(
                f"""SELECT COUNT(*) FROM {table} AS child
                    LEFT JOIN {parent_table} AS parent ON parent.id = child.{foreign_key}
                    WHERE parent.id IS NULL"""
            ).fetchone()[0]
            if count:
                problems.append(f"{table} 存在 {count} 条孤立记录")

        counter_rows = self.connection.execute(
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
        if counter_rows:
            problems.append(f"{len(counter_rows)} 个扫描任务的进度计数与文件记录不一致")
        return tuple(problems)

    @staticmethod
    def _stored_schema_version(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        return int(row["value"]) if row is not None else 0

    @staticmethod
    def _store_schema_version(connection: sqlite3.Connection, version: int) -> None:
        connection.execute(
            """INSERT INTO schema_meta(key, value) VALUES ('schema_version', ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (str(version),),
        )

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        names = {row["name"] for row in rows}
        missing = sorted(_REQUIRED_TABLES - names)
        if missing:
            raise RuntimeError(f"数据库缺少必要表：{', '.join(missing)}")


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
        now = utc_now()
        self._connection.execute(
            "UPDATE scan_jobs SET status = ?, updated_at = ?, completed_at = ? WHERE id = ?",
            (status, now, now if completed else None, scan_id),
        )

    def update_progress(self, scan_id: str, seen: int, completed: int, bytes_hashed: int) -> None:
        """在当前批次内更新可恢复进度。"""

        self._require_active()
        self._connection.execute(
            """UPDATE scan_jobs SET files_seen = ?, files_hashed = ?, bytes_hashed = ?,
               updated_at = ? WHERE id = ?""",
            (seen, completed, bytes_hashed, utc_now(), scan_id),
        )

    def record_volume(self, scan_id: str, values: dict[str, Any]) -> None:
        """在当前批次内替换扫描对应的卷信息。"""

        self._require_active()
        columns = (
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
        self._connection.execute("DELETE FROM volumes WHERE scan_id = ?", (scan_id,))
        self._connection.execute(
            f"INSERT INTO volumes(scan_id, {', '.join(columns)}) VALUES (?, {', '.join('?' for _ in columns)})",
            (scan_id, *(values.get(column) for column in columns)),
        )

    def record_directory(
        self,
        scan_id: str,
        relative_path: str,
        path_key: str,
        parent_path_key: str | None,
        error: str | None = None,
    ) -> None:
        """在当前批次内插入或更新目录记录。"""

        self._require_active()
        self._connection.execute(
            """INSERT INTO directories(
                   scan_id, relative_path, path_key, parent_path_key, scan_status, error_message
               ) VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(scan_id, path_key) DO UPDATE SET
                   scan_status = excluded.scan_status, error_message = excluded.error_message""",
            (
                scan_id,
                relative_path,
                path_key,
                parent_path_key,
                "ERROR" if error else "OK",
                error,
            ),
        )

    def record_error(
        self, scan_id: str, relative_path: str | None, code: str, message: str
    ) -> None:
        """在当前批次内写入可追踪错误。"""

        self._require_active()
        self._connection.execute(
            """INSERT INTO scan_errors(
                   scan_id, relative_path, error_code, error_message, created_at
               ) VALUES (?, ?, ?, ?, ?)""",
            (scan_id, relative_path, code, message, utc_now()),
        )

    def record_file(self, scan_id: str, item: dict[str, Any]) -> None:
        """在当前批次内插入或更新文件 Hash 结果。"""

        self._require_active()
        columns = (
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
            "hash_status",
            "attempt_count",
            "error_code",
            "error_message",
            "hashed_at",
        )
        values = [item.get(column) for column in columns]
        assignments = ", ".join(
            f"{column} = excluded.{column}"
            for column in columns
            if column not in {"relative_path", "path_key"}
        )
        self._connection.execute(
            f"""INSERT INTO files(scan_id, {", ".join(columns)})
                VALUES (?, {", ".join("?" for _ in columns)})
                ON CONFLICT(scan_id, path_key) DO UPDATE SET {assignments}""",
            (scan_id, *values),
        )

    def set_compare_status(
        self,
        compare_id: str,
        status: str,
        summary: dict[str, int] | None = None,
        completed: bool = False,
    ) -> None:
        """在当前批次内更新比较状态和摘要。"""

        self._require_active()
        self._connection.execute(
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

    def record_compare_entry(self, compare_id: str, item: dict[str, Any]) -> None:
        """在当前批次内写入一条比较结果。"""

        self._require_active()
        status = CompareStatus(item["status"])
        self._connection.execute(
            """INSERT INTO compare_entries(
                   compare_id, relative_path, status, old_size_bytes, new_size_bytes,
                   old_sha256, new_sha256, error_message
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                compare_id,
                item["relative_path"],
                status,
                item.get("old_size_bytes"),
                item.get("new_size_bytes"),
                item.get("old_sha256"),
                item.get("new_sha256"),
                item.get("error_message"),
            ),
        )

    def _require_active(self) -> None:
        if not self._active:
            raise RuntimeError("批量写入器尚未开启或已经关闭")

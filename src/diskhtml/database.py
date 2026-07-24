"""SQLite 数据库、迁移和流式查询接口。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .models import ScanStatus, validate_scan_transition
from .util import utc_now

SCHEMA_VERSION = "1"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
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
);
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
);
CREATE TABLE IF NOT EXISTS directories (
    id INTEGER PRIMARY KEY,
    scan_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    path_key TEXT NOT NULL,
    parent_path_key TEXT,
    scan_status TEXT NOT NULL DEFAULT 'OK',
    error_message TEXT,
    UNIQUE(scan_id, path_key)
);
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
);
CREATE TABLE IF NOT EXISTS scan_errors (
    id INTEGER PRIMARY KEY,
    scan_id TEXT NOT NULL,
    relative_path TEXT,
    error_code TEXT NOT NULL,
    error_message TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS compare_jobs (
    id TEXT PRIMARY KEY,
    left_source TEXT NOT NULL,
    right_source TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    summary_json TEXT NOT NULL DEFAULT '{}'
);
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
);
CREATE INDEX IF NOT EXISTS idx_files_scan_status ON files(scan_id, hash_status);
CREATE INDEX IF NOT EXISTS idx_files_scan_path ON files(scan_id, path_key, size_bytes, sha256);
CREATE INDEX IF NOT EXISTS idx_directories_scan_parent ON directories(scan_id, parent_path_key);
CREATE INDEX IF NOT EXISTS idx_compare_entries_job ON compare_entries(compare_id, status, relative_path);
"""


class Database:
    """封装单个项目的 SQLite 数据库。调用方始终是唯一写入者。"""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = NORMAL")
        self.migrate()

    def close(self) -> None:
        """关闭数据库连接。"""

        self.connection.close()

    def migrate(self) -> None:
        """创建首版表结构并校验模式版本。"""

        with self.connection:
            self.connection.executescript(SCHEMA_SQL)
            row = self.connection.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                self.connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES (?, ?)",
                    ("schema_version", SCHEMA_VERSION),
                )
            elif row["value"] != SCHEMA_VERSION:
                raise RuntimeError(f"不支持的数据库模式版本：{row['value']}")

    def create_scan(self, source_type: str, source_path: str, options: dict[str, Any]) -> str:
        """创建等待执行的扫描任务。"""

        scan_id = str(uuid.uuid4())
        now = utc_now()
        with self.connection:
            self.connection.execute(
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
                    SCHEMA_VERSION,
                ),
            )
        return scan_id

    def get_scan(self, scan_id: str) -> sqlite3.Row | None:
        """取得一个扫描任务。"""

        return self.connection.execute(
            "SELECT * FROM scan_jobs WHERE id = ?", (scan_id,)
        ).fetchone()

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
        now = utc_now()
        with self.connection:
            self.connection.execute(
                "UPDATE scan_jobs SET status = ?, updated_at = ?, completed_at = ? WHERE id = ?",
                (status, now, now if completed else None, scan_id),
            )

    def update_progress(self, scan_id: str, seen: int, completed: int, bytes_hashed: int) -> None:
        """保存可恢复的进度计数。"""

        with self.connection:
            self.connection.execute(
                """UPDATE scan_jobs SET files_seen = ?, files_hashed = ?, bytes_hashed = ?,
                   updated_at = ? WHERE id = ?""",
                (seen, completed, bytes_hashed, utc_now(), scan_id),
            )

    def record_volume(self, scan_id: str, values: dict[str, Any]) -> None:
        """记录扫描时采集到的卷信息。"""

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
        with self.connection:
            self.connection.execute("DELETE FROM volumes WHERE scan_id = ?", (scan_id,))
            self.connection.execute(
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
        """插入或更新一个目录记录。"""

        with self.connection:
            self.connection.execute(
                """INSERT INTO directories(scan_id, relative_path, path_key, parent_path_key, scan_status, error_message)
                   VALUES (?, ?, ?, ?, ?, ?)
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
        """保留不可忽略的扫描错误。"""

        with self.connection:
            self.connection.execute(
                "INSERT INTO scan_errors(scan_id, relative_path, error_code, error_message, created_at) VALUES (?, ?, ?, ?, ?)",
                (scan_id, relative_path, code, message, utc_now()),
            )

    def get_file(self, scan_id: str, path_key: str) -> sqlite3.Row | None:
        """按比较键取得已有文件记录，用于恢复时跳过稳定结果。"""

        return self.connection.execute(
            "SELECT * FROM files WHERE scan_id = ? AND path_key = ?", (scan_id, path_key)
        ).fetchone()

    def record_file(self, scan_id: str, item: dict[str, Any]) -> None:
        """以事务方式插入或更新文件 Hash 结果。"""

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
        with self.connection:
            self.connection.execute(
                f"""INSERT INTO files(scan_id, {", ".join(columns)})
                    VALUES (?, {", ".join("?" for _ in columns)})
                    ON CONFLICT(scan_id, path_key) DO UPDATE SET {assignments}""",
                (scan_id, *values),
            )

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

    def integrity_check(self) -> str:
        """执行 SQLite 自检。"""

        return self.connection.execute("PRAGMA integrity_check").fetchone()[0]

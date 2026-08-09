"""SQLite 模式声明、版本读写与结构校验。"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 3

CREATE_SCHEMA_META = """
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
        hash_algorithm TEXT NOT NULL,
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
        old_hash_algorithm TEXT,
        new_hash_algorithm TEXT,
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

_MIGRATION_3 = (
    "ALTER TABLE directories ADD COLUMN created_time TEXT",
    "ALTER TABLE directories ADD COLUMN modified_time TEXT",
)

MIGRATIONS: dict[int, tuple[str, ...]] = {1: _MIGRATION_1, 2: _MIGRATION_2, 3: _MIGRATION_3}
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
_REQUIRED_COLUMNS = {
    "files": frozenset({"hash_algorithm"}),
    "compare_entries": frozenset({"old_hash_algorithm", "new_hash_algorithm"}),
}


def stored_schema_version(connection: sqlite3.Connection) -> int:
    """读取模式版本；尚未记录时返回零。"""

    row = connection.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()
    return int(row["value"]) if row is not None else 0


def store_schema_version(connection: sqlite3.Connection, version: int) -> None:
    """写入当前模式版本。"""

    connection.execute(
        """INSERT INTO schema_meta(key, value) VALUES ('schema_version', ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
        (str(version),),
    )


def validate_schema(connection: sqlite3.Connection) -> None:
    """确认当前模式所需的表和兼容字段全部存在。"""

    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    names = {row["name"] for row in rows}
    missing = sorted(_REQUIRED_TABLES - names)
    if missing:
        raise RuntimeError(f"数据库缺少必要表：{', '.join(missing)}")

    for table, required_columns in _REQUIRED_COLUMNS.items():
        column_rows = connection.execute(f"PRAGMA table_info({table})")
        columns = {row["name"] for row in column_rows}
        missing_columns = sorted(required_columns - columns)
        if missing_columns:
            raise RuntimeError(
                f"数据库表 {table} 缺少当前版本字段：{', '.join(missing_columns)}；"
                "旧数据库不兼容，请重新生成"
            )

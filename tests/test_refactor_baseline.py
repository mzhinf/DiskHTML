"""现代化重构期间的公共 API、CLI、数据格式和快照语义基线。"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import diskhtml
from diskhtml import html_archive, report, sampled_hash
from diskhtml.cli import build_parser as build_advanced_parser
from diskhtml.config import AppConfig, ScanConfig
from diskhtml.database import SCHEMA_VERSION, Database
from diskhtml.exe_cli import build_parser as build_exe_parser
from diskhtml.models import (
    CompareResult,
    CompareStatus,
    ErrorCode,
    ErrorRecord,
    FileRecord,
    HashStatus,
    ScanJob,
    ScanStatus,
    SourceType,
    VolumeInfo,
)
from diskhtml.scanner import ScanOptions

_PROJECT_ROOT = Path(__file__).parents[1]
_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "refactor_baseline"


def _command_names(parser: argparse.ArgumentParser) -> tuple[str, ...]:
    """按注册顺序返回解析器的子命令名称。"""

    action = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    return tuple(action.choices)


class PublicApiBaselineTests(TestCase):
    """固定重构期间必须保留的导出、兼容名称和格式版本。"""

    def test_explicit_exports_are_stable(self) -> None:
        """显式导出集合不得在普通重构中缩减或改名。"""

        self.assertEqual(["__version__"], diskhtml.__all__)
        self.assertEqual(["export_compare", "export_scan"], report.__all__)
        self.assertEqual(
            [
                "FULL_SHA256_ALGORITHM",
                "DEFAULT_SAMPLE_TARGET_BYTES",
                "DEFAULT_SAMPLE_COUNT",
                "MAX_SAMPLE_COUNT",
                "FileChangedDuringHashError",
                "SampledHashResult",
                "sampled_sha256",
                "sampled_sha256_algorithm",
            ],
            sampled_hash.__all__,
        )

    def test_compatibility_names_are_stable(self) -> None:
        """扫描配置别名和公开命名领域记录应继续可导入。"""

        self.assertIs(ScanOptions, ScanConfig)
        for record_type in (
            ScanJob,
            VolumeInfo,
            FileRecord,
            CompareResult,
            ErrorRecord,
        ):
            with self.subTest(record_type=record_type.__name__):
                self.assertEqual("diskhtml.models", record_type.__module__)

    def test_versions_and_state_values_are_stable(self) -> None:
        """配置、HTML、SQLite 版本和领域状态值不得被结构重构改变。"""

        self.assertEqual(1, AppConfig().format_version)
        self.assertEqual(2, html_archive._ARCHIVE_FORMAT_VERSION)
        self.assertEqual(3, SCHEMA_VERSION)
        self.assertEqual(("FILE", "DIRECTORY", "VOLUME"), tuple(SourceType))
        self.assertEqual(
            ("PENDING", "SCANNING", "PAUSED", "COMPLETED", "CANCELLED", "FAILED"),
            tuple(ScanStatus),
        )
        self.assertEqual(("PENDING", "HASHING", "OK", "UNSTABLE", "ERROR"), tuple(HashStatus))
        self.assertEqual(
            ("MATCH", "PRECHECK_MATCH", "CHANGED", "ADDED", "MISSING", "ERROR"),
            tuple(CompareStatus),
        )
        self.assertEqual(
            (
                "SOURCE_NOT_FOUND",
                "PERMISSION_DENIED",
                "ENTRY_ERROR",
                "READ_ERROR",
                "FILE_DISAPPEARED",
                "CHANGED_DURING_HASH",
                "PATH_COLLISION",
                "DATABASE_ERROR",
                "VOLUME_INFO_ERROR",
                "UNKNOWN",
            ),
            tuple(ErrorCode),
        )

    def test_cli_commands_and_help_are_stable(self) -> None:
        """两套 CLI 的命令集合和固定宽度帮助输出应保持一致。"""

        with patch.dict(os.environ, {"COLUMNS": "80", "LINES": "24"}):
            advanced = build_advanced_parser()
            executable = build_exe_parser()
        self.assertEqual(
            (
                "init-db",
                "check-db",
                "check-project",
                "scan",
                "snapshot",
                "render-sqlite",
                "compare-source",
                "compare-html",
                "resume",
                "status",
                "export",
                "compare",
                "verify",
                "import",
            ),
            _command_names(advanced),
        )
        self.assertEqual(
            ("snapshot", "render-sqlite", "compare-source"), _command_names(executable)
        )
        self.assertEqual(
            (_FIXTURE_ROOT / "advanced_help.txt").read_text(encoding="utf-8"),
            advanced.format_help(),
        )
        self.assertEqual(
            (_FIXTURE_ROOT / "exe_help.txt").read_text(encoding="utf-8"),
            executable.format_help(),
        )


class DatabaseSchemaBaselineTests(TestCase):
    """固定不涉及格式迁移的 SQLite 表、列和索引语义。"""

    def test_schema_shape_is_stable(self) -> None:
        """结构重构前后必须生成相同的表、列顺序和索引名称。"""

        expected_columns = {
            "schema_meta": ("key", "value"),
            "migration_history": ("version", "applied_at"),
            "scan_jobs": (
                "id",
                "source_type",
                "source_path",
                "status",
                "hash_algorithm",
                "options_json",
                "started_at",
                "updated_at",
                "completed_at",
                "files_seen",
                "files_hashed",
                "bytes_hashed",
                "format_version",
            ),
            "volumes": (
                "id",
                "scan_id",
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
            ),
            "directories": (
                "id",
                "scan_id",
                "relative_path",
                "path_key",
                "parent_path_key",
                "scan_status",
                "error_message",
                "created_time",
                "modified_time",
            ),
            "files": (
                "id",
                "scan_id",
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
            ),
            "scan_errors": (
                "id",
                "scan_id",
                "relative_path",
                "error_code",
                "error_message",
                "created_at",
            ),
            "compare_jobs": (
                "id",
                "left_source",
                "right_source",
                "status",
                "created_at",
                "completed_at",
                "summary_json",
            ),
            "compare_entries": (
                "id",
                "compare_id",
                "relative_path",
                "status",
                "old_size_bytes",
                "new_size_bytes",
                "old_sha256",
                "new_sha256",
                "old_hash_algorithm",
                "new_hash_algorithm",
                "error_message",
            ),
        }
        expected_indexes = (
            "idx_compare_entries_job",
            "idx_directories_scan_parent",
            "idx_errors_scan_path",
            "idx_files_scan_path",
            "idx_files_scan_status",
        )
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with Database(Path(directory) / "baseline.sqlite3") as database:
                actual_columns = {
                    table: tuple(
                        row["name"]
                        for row in database.connection.execute(f'PRAGMA table_info("{table}")')
                    )
                    for table in expected_columns
                }
                actual_indexes = tuple(
                    row["name"]
                    for row in database.connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type = 'index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                    )
                )
        self.assertEqual(expected_columns, actual_columns)
        self.assertEqual(expected_indexes, actual_indexes)


class HtmlSemanticBaselineTests(TestCase):
    """固定包含特殊路径和混合 Hash 算法的快照载荷语义。"""

    def test_snapshot_payload_semantics_are_stable(self) -> None:
        """忽略时间和绝对路径后，文件字段、顺序和摘要应保持不变。"""

        text_payload = "中文".encode()
        large_payload = bytes(range(64))
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "来源"
            source.mkdir()
            (source / "资料 & 特殊.txt").write_bytes(text_payload)
            (source / "空.txt").write_bytes(b"")
            (source / "large.bin").write_bytes(large_payload)
            output = root / "baseline.html"
            html_archive.create_html_snapshot(
                source,
                output,
                ScanConfig(
                    workers=1,
                    queue_size=1,
                    chunk_size=8,
                    hash_mode="sampled",
                    sample_target_bytes=8,
                    sample_count=4,
                ),
            )
            payload = html_archive.read_html_snapshot(output)

        files = {item["relative_path"]: item for item in payload["files"]}
        expected_paths = ("large.bin", "空.txt", "资料 & 特殊.txt")
        self.assertEqual("scan", payload["kind"])
        self.assertEqual(2, payload["format_version"])
        self.assertEqual(list(expected_paths), [item["relative_path"] for item in payload["files"]])
        self.assertEqual(
            sampled_hash.sampled_sha256_algorithm(8, 4), payload["scan"]["hash_algorithm"]
        )
        self.assertEqual(
            sampled_hash.sampled_sha256_algorithm(8, 4), files["large.bin"]["hash_algorithm"]
        )
        self.assertEqual("full-sha256", files["空.txt"]["hash_algorithm"])
        self.assertEqual("full-sha256", files["资料 & 特殊.txt"]["hash_algorithm"])
        self.assertEqual(hashlib.sha256(b"").hexdigest().upper(), files["空.txt"]["sha256"])
        self.assertEqual(
            hashlib.sha256(text_payload).hexdigest().upper(),
            files["资料 & 特殊.txt"]["sha256"],
        )
        self.assertEqual({"OK"}, {item["hash_status"] for item in payload["files"]})


if __name__ == "__main__":
    import unittest

    unittest.main()

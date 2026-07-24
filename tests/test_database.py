"""SQLite 迁移、事务、仓储和流式写入测试。"""

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from diskhtml.database import MIGRATIONS, SCHEMA_VERSION, Database
from diskhtml.models import CompareStatus, ScanStatus


class DatabaseTests(TestCase):
    """验证阶段 2 所需的数据库行为。"""

    def test_database_initializes_latest_schema_and_integrity_check(self) -> None:
        """新数据库应创建最新模式、迁移记录并通过自检。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with Database(Path(directory) / "archive.sqlite3") as database:
                self.assertEqual(database.schema_version(), SCHEMA_VERSION)
                self.assertEqual(database.migration_versions(), (2, 3))
                self.assertEqual(database.integrity_check(), "ok")
                self.assertEqual(database.project_check(), ())

    def test_project_check_reports_orphans_and_inconsistent_counters(self) -> None:
        """项目自校验应报告孤立记录和扫描进度与文件记录不一致的问题。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with Database(Path(directory) / "archive.sqlite3") as database:
                scan_id = database.create_scan("DIRECTORY", "C:/data", {})
                database.connection.execute(
                    """INSERT INTO scan_errors(scan_id, relative_path, error_code, error_message, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    ("missing-scan", None, "READ_ERROR", "模拟孤立记录", "2026-07-24T00:00:00Z"),
                )
                database.connection.execute(
                    "UPDATE scan_jobs SET files_hashed = 1 WHERE id = ?", (scan_id,)
                )
                database.connection.commit()

                problems = database.project_check()

        self.assertTrue(any("scan_errors" in problem for problem in problems))
        self.assertTrue(any("进度计数" in problem for problem in problems))

    def test_legacy_version_one_database_is_migrated(self) -> None:
        """版本 1 项目应原地升级到当前版本。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                for statement in MIGRATIONS[1]:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES ('schema_version', '1')"
                )
                connection.commit()
            finally:
                connection.close()

            with Database.open_existing(path) as database:
                self.assertEqual(database.schema_version(), SCHEMA_VERSION)
                self.assertEqual(database.migration_versions(), (2, 3))
                self.assertEqual(database.integrity_check(), "ok")

    def test_newer_schema_is_rejected_without_downgrade(self) -> None:
        """比当前程序更新的项目数据库不能被静默写入。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "future.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES ('schema_version', '999')"
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(RuntimeError, "新于当前程序"):
                Database.open_existing(path)

    def test_database_enforces_scan_state_machine(self) -> None:
        """数据访问层不能把已完成任务重新改为运行中。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with Database(Path(directory) / "archive.sqlite3") as database:
                scan_id = database.create_scan("DIRECTORY", "C:/data", {})
                database.set_scan_status(scan_id, ScanStatus.SCANNING)
                database.set_scan_status(scan_id, ScanStatus.COMPLETED, completed=True)
                with self.assertRaisesRegex(ValueError, "不允许"):
                    database.set_scan_status(scan_id, ScanStatus.SCANNING)

    def test_failed_batch_rolls_back_every_record(self) -> None:
        """异常批次不得留下半成品文件或错误记录。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with Database(Path(directory) / "archive.sqlite3") as database:
                scan_id = database.create_scan("DIRECTORY", "C:/data", {})
                with self.assertRaisesRegex(RuntimeError, "模拟中断"):
                    with database.batch() as batch:
                        batch.record_file(scan_id, self._file_item("a.txt", "a.txt"))
                        batch.record_error(scan_id, "a.txt", "READ_ERROR", "模拟错误")
                        raise RuntimeError("模拟中断")
                self.assertIsNone(database.get_file(scan_id, "a.txt"))
                self.assertEqual(tuple(database.iter_errors(scan_id)), ())
                self.assertEqual(database.integrity_check(), "ok")

    def test_batch_streams_ten_thousand_records(self) -> None:
        """批量写入和按路径遍历应支持大量记录且无需预先汇总。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with Database(Path(directory) / "archive.sqlite3") as database:
                scan_id = database.create_scan("DIRECTORY", "C:/data", {})
                with database.batch() as batch:
                    for number in range(10_000):
                        path = f"files/{number:05d}.bin"
                        batch.record_file(scan_id, self._file_item(path, path, number))
                    batch.update_progress(scan_id, 10_000, 10_000, 49_995_000)
                self.assertEqual(sum(1 for _ in database.iter_files(scan_id)), 10_000)
                self.assertEqual(database.summary(scan_id)["hashed_files"], 10_000)
                self.assertEqual(database.get_scan(scan_id)["files_hashed"], 10_000)

    def test_compare_repository_writes_and_streams_entries(self) -> None:
        """比较任务及其明细应通过同一批量事务持久化。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with Database(Path(directory) / "archive.sqlite3") as database:
                compare_id = database.create_compare("left", "right")
                with database.batch() as batch:
                    batch.record_compare_entry(
                        compare_id,
                        {
                            "relative_path": "same.txt",
                            "status": CompareStatus.MATCH,
                            "old_size_bytes": 3,
                            "new_size_bytes": 3,
                            "old_sha256": "A",
                            "new_sha256": "A",
                        },
                    )
                    batch.record_compare_entry(
                        compare_id,
                        {
                            "relative_path": "new.txt",
                            "status": CompareStatus.ADDED,
                            "new_size_bytes": 2,
                            "new_sha256": "B",
                        },
                    )
                    batch.set_compare_status(
                        compare_id,
                        "COMPLETED",
                        {"MATCH": 1, "ADDED": 1},
                        completed=True,
                    )
                entries = tuple(database.iter_compare_entries(compare_id))
                self.assertEqual([entry["status"] for entry in entries], ["ADDED", "MATCH"])
                self.assertEqual(database.get_compare(compare_id)["status"], "COMPLETED")

    @staticmethod
    def _file_item(relative_path: str, path_key: str, size_bytes: int = 0) -> dict[str, object]:
        """构造稳定的成功文件记录。"""

        return {
            "relative_path": relative_path,
            "path_key": path_key,
            "name": Path(relative_path).name,
            "extension": Path(relative_path).suffix,
            "size_bytes": size_bytes,
            "created_time": "2026-07-24T00:00:00Z",
            "modified_time": "2026-07-24T00:00:00Z",
            "mtime_ns": 0,
            "sha256": "A" * 64,
            "sha512": None,
            "hash_status": "OK",
            "attempt_count": 1,
            "error_code": None,
            "error_message": None,
            "hashed_at": "2026-07-24T00:00:00Z",
        }

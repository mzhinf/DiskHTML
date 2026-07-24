"""SQLite 建表、版本和状态转换测试。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from diskhtml.database import SCHEMA_VERSION, Database
from diskhtml.models import ScanStatus


class DatabaseTests(TestCase):
    """验证阶段 1 所需的迁移框架。"""

    def test_database_initializes_and_passes_integrity_check(self) -> None:
        """空数据库应创建首版模式并通过自检。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            database = Database(Path(directory) / "archive.sqlite3")
            try:
                version = database.connection.execute(
                    "SELECT value FROM schema_meta WHERE key = 'schema_version'"
                ).fetchone()[0]
                self.assertEqual(version, SCHEMA_VERSION)
                self.assertEqual(database.integrity_check(), "ok")
            finally:
                database.close()

    def test_database_enforces_scan_state_machine(self) -> None:
        """数据访问层不能把已完成任务重新改为运行中。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            database = Database(Path(directory) / "archive.sqlite3")
            try:
                scan_id = database.create_scan("DIRECTORY", "C:/data", {})
                database.set_scan_status(scan_id, ScanStatus.SCANNING)
                database.set_scan_status(scan_id, ScanStatus.COMPLETED, completed=True)
                with self.assertRaisesRegex(ValueError, "不允许"):
                    database.set_scan_status(scan_id, ScanStatus.SCANNING)
            finally:
                database.close()

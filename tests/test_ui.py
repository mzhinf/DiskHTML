"""PyQt6 项目窗口测试。"""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from diskhtml.database import Database
from diskhtml.models import ScanStatus
from diskhtml.ui import MainWindow


class UiTests(TestCase):
    """验证项目窗口通过公共数据库接口读取任务。"""

    @classmethod
    def setUpClass(cls) -> None:
        """创建测试共享的离屏 Qt 应用。"""

        cls.application = QApplication.instance() or QApplication([])

    def test_window_loads_scan_rows_from_project(self) -> None:
        """打开项目后，表格应显示持久化扫描任务。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "archive.sqlite3"
            with Database(path) as database:
                scan_id = database.create_scan("DIRECTORY", "C:/资料", {})
                database.set_scan_status(scan_id, ScanStatus.SCANNING)
                database.set_scan_status(scan_id, ScanStatus.COMPLETED, completed=True)
            window = MainWindow(path)
            self.assertEqual(window._table.rowCount(), 1)
            self.assertEqual(window._table.item(0, 1).text(), "COMPLETED")
            self.assertIn("archive.sqlite3", window.windowTitle())
            window.close()

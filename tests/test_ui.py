"""PyQt6 项目窗口测试。"""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

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

    def test_open_report_uses_system_browser(self) -> None:
        """\u9009\u62e9 HTML \u62a5\u544a\u540e\u5e94\u59d4\u6258\u7cfb\u7edf\u9ed8\u8ba4\u6d4f\u89c8\u5668\u6253\u5f00\u672c\u5730\u6587\u4ef6\u3002"""

        report_path = Path.cwd() / "report.html"
        window = MainWindow()
        with (
            patch(
                "diskhtml.ui.QFileDialog.getOpenFileName",
                return_value=(str(report_path), ""),
            ),
            patch("diskhtml.ui.QDesktopServices.openUrl", return_value=True) as opener,
        ):
            window.open_report()
        self.assertEqual(Path(opener.call_args.args[0].toLocalFile()), report_path)
        window.close()

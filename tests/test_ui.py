"""PyQt6 项目窗口测试。"""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from diskhtml.database import Database
from diskhtml.models import ScanProgress, ScanStatus
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

    def test_scan_progress_updates_status_bar(self) -> None:
        """\u626b\u63cf\u8fdb\u5ea6\u5feb\u7167\u5e94\u66f4\u65b0\u72b6\u6001\u680f\u5e76\u663e\u793a\u6307\u793a\u5668\u3002"""

        window = MainWindow()
        window._scan_progress(
            ScanProgress("scan-1", 5, 3, 2 * 1024 * 1024, "data/a.bin", 1024 * 1024, 12)
        )
        self.assertIn("3/5", window.statusBar().currentMessage())
        self.assertIn("data/a.bin", window.statusBar().currentMessage())
        self.assertFalse(window._scan_progress_bar.isHidden())
        window.close()

    def test_load_scan_config_uses_selected_toml(self) -> None:
        """\u9009\u62e9\u914d\u7f6e\u6587\u4ef6\u540e\u5e94\u4f7f\u7528\u5176\u626b\u63cf\u4e0e\u6392\u9664\u89c4\u5219\u3002"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            config_path = Path(directory) / "scan.toml"
            config_path.write_text(
                '[scan]\nworkers = 4\nexclude_dirs = ["cache"]\n', encoding="utf-8"
            )
            window = MainWindow()
            with patch(
                "diskhtml.ui.QFileDialog.getOpenFileName", return_value=(str(config_path), "")
            ):
                window.load_scan_config()
            self.assertEqual(window._scan_config.workers, 4)
            self.assertEqual(window._scan_config.exclude_dirs, ("cache",))

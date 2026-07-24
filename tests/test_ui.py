"""PyQt6 项目窗口测试。"""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QItemSelectionModel
from PyQt6.QtWidgets import QApplication, QComboBox, QTableWidget

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

    def test_recover_selected_scan_starts_background_thread(self) -> None:
        """选中已取消任务后应创建后台恢复线程。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "archive.sqlite3"
            with Database(path) as database:
                scan_id = database.create_scan("DIRECTORY", "C:/data", {})
                database.set_scan_status(scan_id, ScanStatus.SCANNING)
                database.set_scan_status(scan_id, ScanStatus.CANCELLED)
            window = MainWindow(path)
            window._table.selectRow(0)
            with patch("diskhtml.ui.ScanThread") as thread_class:
                window.recover_selected_scan()
            self.assertEqual(thread_class.call_args.args[:2], (path, None))
            self.assertEqual(thread_class.call_args.kwargs["resume_scan_id"], scan_id)
            thread_class.return_value.start.assert_called_once_with()
            window.close()

    def test_show_selected_errors_displays_persisted_errors(self) -> None:
        """选中含错误的扫描时应显示已持久化的错误明细。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "archive.sqlite3"
            with Database(path) as database:
                scan_id = database.create_scan("DIRECTORY", "C:/data", {})
                database.record_error(scan_id, "missing.txt", "READ_ERROR", "无法读取文件")
            window = MainWindow(path)
            window._table.selectRow(0)
            with patch("diskhtml.ui.QDialog.exec", return_value=0):
                window.show_selected_errors()
            table = window._error_dialog.findChild(QTableWidget, "scan_error_table")
            self.assertIsNotNone(table)
            self.assertEqual(table.rowCount(), 1)
            self.assertEqual(table.item(0, 1).text(), "READ_ERROR")
            window.close()

    def test_compare_selected_scans_starts_background_thread(self) -> None:
        """选中两个完成快照后应创建后台比较线程。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "archive.sqlite3"
            with Database(path) as database:
                left_id = database.create_scan("DIRECTORY", "C:/left", {})
                database.set_scan_status(left_id, ScanStatus.SCANNING)
                database.set_scan_status(left_id, ScanStatus.COMPLETED, completed=True)
                right_id = database.create_scan("DIRECTORY", "C:/right", {})
                database.set_scan_status(right_id, ScanStatus.SCANNING)
                database.set_scan_status(right_id, ScanStatus.COMPLETED, completed=True)
            window = MainWindow(path)
            window._table.selectRow(0)
            window._table.selectionModel().select(
                window._table.model().index(1, 0),
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )
            with patch("diskhtml.ui.CompareThread") as thread_class:
                window.compare_selected_scans()
            self.assertEqual(thread_class.call_args.args[0], path)
            self.assertEqual(set(thread_class.call_args.args[1:]), {left_id, right_id})
            thread_class.return_value.start.assert_called_once_with()
            window.close()

    def test_show_last_compare_filters_persisted_entries(self) -> None:
        """比较结果对话框应显示并按状态筛选持久化条目。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "archive.sqlite3"
            with Database(path) as database:
                compare_id = database.create_compare("scan:left", "scan:right")
                database.set_compare_status(compare_id, "RUNNING")
                database.record_compare_entry(
                    compare_id, {"relative_path": "added.txt", "status": "ADDED"}
                )
                database.record_compare_entry(
                    compare_id, {"relative_path": "same.txt", "status": "MATCH"}
                )
                database.set_compare_status(compare_id, "COMPLETED", {"ADDED": 1, "MATCH": 1}, True)
            window = MainWindow(path)
            window._last_compare_id = compare_id
            with patch("diskhtml.ui.QDialog.exec", return_value=0):
                window.show_last_compare()
            table = window._compare_dialog.findChild(QTableWidget, "compare_result_table")
            filter_box = window._compare_dialog.findChild(QComboBox, "compare_status_filter")
            self.assertEqual(table.rowCount(), 2)
            filter_box.setCurrentText("ADDED")
            self.assertFalse(table.isRowHidden(0))
            self.assertTrue(table.isRowHidden(1))
            window.close()

    def test_start_file_scan_uses_background_thread(self) -> None:
        """选择单个文件后应创建后台扫描线程。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "archive.sqlite3"
            source = Path(directory) / "sample.bin"
            source.write_bytes(b"content")
            with Database(path):
                pass
            window = MainWindow(path)
            with (
                patch("diskhtml.ui.QFileDialog.getOpenFileName", return_value=(str(source), "")),
                patch("diskhtml.ui.ScanThread") as thread_class,
            ):
                window.start_file_scan()
            self.assertEqual(thread_class.call_args.args[:2], (path, source))
            thread_class.return_value.start.assert_called_once_with()
            window.close()

    def test_compare_directory_to_selected_scan_starts_background_thread(self) -> None:
        """选择历史快照与当前目录后应创建后台比较线程。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "archive.sqlite3"
            source = Path(directory) / "current"
            source.mkdir()
            with Database(path) as database:
                scan_id = database.create_scan("DIRECTORY", "C:/history", {})
                database.set_scan_status(scan_id, ScanStatus.SCANNING)
                database.set_scan_status(scan_id, ScanStatus.COMPLETED, completed=True)
            window = MainWindow(path)
            window._table.selectRow(0)
            with (
                patch("diskhtml.ui.QFileDialog.getExistingDirectory", return_value=str(source)),
                patch("diskhtml.ui.CompareSourceThread") as thread_class,
            ):
                window.compare_directory_to_selected_scan()
            self.assertEqual(thread_class.call_args.args[:3], (path, source, scan_id))
            thread_class.return_value.start.assert_called_once_with()
            window.close()

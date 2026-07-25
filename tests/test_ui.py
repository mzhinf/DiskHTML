"""DiskHTML 桌面生成界面测试。"""

import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from unittest import TestCase
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPushButton, QTabWidget

from diskhtml import ui_text
from diskhtml.config import ScanConfig
from diskhtml.html_archive import create_html_snapshot, sqlite_snapshot_path
from diskhtml.models import ScanProgress
from diskhtml.ui import ArchiveDirectoryDialog, MainWindow


class UiTests(TestCase):
    """验证三页签输入、内联校验与后台任务。"""

    @classmethod
    def setUpClass(cls) -> None:
        """创建测试共享的离屏 Qt 应用。"""

        cls.application = QApplication.instance() or QApplication([])

    def test_window_has_three_task_tabs_and_no_permanent_controls(self) -> None:
        """窗口只显示三个任务页，控制区初始隐藏。"""

        window = MainWindow()
        tabs = window.findChild(QTabWidget)
        self.assertEqual(
            [tabs.tabText(index) for index in range(tabs.count())],
            [
                ui_text.TAB_SNAPSHOT,
                ui_text.TAB_COMPARE,
                ui_text.TAB_SQLITE,
            ],
        )
        labels = {button.text() for button in window.findChildren(QPushButton)}
        self.assertTrue(
            {ui_text.CREATE_SNAPSHOT, ui_text.CREATE_COMPARE, ui_text.CREATE_SQLITE} <= labels
        )
        self.assertTrue(window._run_panel.isHidden())
        self.assertTrue(window._result_panel.isHidden())
        self.assertEqual((window.width(), window.height()), (900, 650))
        self.assertEqual(window.minimumSize(), window.maximumSize())
        self.assertTrue(all(not tabs.tabIcon(index).isNull() for index in range(tabs.count())))
        window.close()

    def test_invalid_compare_inputs_show_inline_errors(self) -> None:
        """比对页的无效输入必须显示字段下方错误。"""

        window = MainWindow()
        window._compare_archive.setText("Z:/missing.html")
        window._compare_source.setText("Z:/missing-directory")
        window._compare_output.setText("Z:/missing/report.html")
        window._start_compare_from_page()
        self.assertFalse(window._compare_archive_error.isHidden())
        self.assertFalse(window._compare_source_error.isHidden())
        self.assertFalse(window._compare_output_error.isHidden())
        window.close()

    def test_snapshot_output_suggestion_includes_short_date(self) -> None:
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "documents"
            source.mkdir()
            window = MainWindow()
            window._snapshot_source.setText(str(source))
            output = root / f"documents_{date.today():%y-%m-%d}.html"
            self.assertEqual(window._snapshot_output.text(), str(output))
            self.assertNotIn("documents-", window._snapshot_output.text())
            self.assertEqual(
                sqlite_snapshot_path(output).name, f"documents_{date.today():%y-%m-%d}.sqlite3"
            )
            window.close()

    def test_snapshot_page_starts_thread_with_follow_links(self) -> None:
        """快照页会将输入、输出和软连接开关传给后台线程。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            output = root / "snapshot.html"
            window = MainWindow()
            window._snapshot_source.setText(str(source))
            window._snapshot_output.setText(str(output))
            window._snapshot_follow.setChecked(True)
            with patch("diskhtml.ui.HtmlSnapshotThread") as thread_class:
                window._start_snapshot_from_page()
            args = thread_class.call_args.args
            self.assertEqual(args[:2], (source, output))
            self.assertTrue(args[2].follow_links)
            thread_class.return_value.start.assert_called_once_with()
            self.assertFalse(window._run_panel.isHidden())
            window.close()

    def test_compare_page_starts_thread_with_selected_directory(self) -> None:
        """比对页将基准快照、子目录和待检查目录传给线程。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            archive = root / "old.html"
            archive.write_text("placeholder", encoding="utf-8")
            source = root / "current"
            source.mkdir()
            output = root / "compare.html"
            window = MainWindow()
            window._compare_archive.setText(str(archive))
            window._compare_source.setText(str(source))
            window._compare_output.setText(str(output))
            window._compare_archive_directory = "folder/photos"
            with (
                patch("diskhtml.ui.html_snapshot_directories", return_value=("", "folder/photos")),
                patch("diskhtml.ui.HtmlDirectoryCompareThread") as thread_class,
            ):
                window._start_compare_from_page()
            args = thread_class.call_args.args
            self.assertEqual(args[:4], (archive, "folder/photos", source, output))
            thread_class.return_value.start.assert_called_once_with()
            window.close()

    def test_progress_and_completion_use_dedicated_panels(self) -> None:
        """运行状态显示在专用区，完成后显示产物路径。"""

        window = MainWindow()
        window._run_panel.show()
        window._scan_progress(
            ScanProgress("scan-1", 5, 3, 2 * 1024 * 1024, "data/a.bin", 1024 * 1024, 12)
        )
        self.assertIn("3/5", window._run_files.text())
        self.assertIn("data/a.bin", window._run_path.text())
        window._snapshot_completed("C:/result.html")
        self.assertTrue(window._run_panel.isHidden())
        self.assertFalse(window._result_panel.isHidden())
        self.assertIn("C:/result.html", window._result_message.text())
        window.close()

    def test_archive_directory_dialog_renders_html_directory_tree(self) -> None:
        """快照内目录选择对话框保留目录层级。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "nested").mkdir()
            (source / "nested" / "one.txt").write_text("content", encoding="utf-8")
            archive = create_html_snapshot(
                source, root / "backup.html", ScanConfig(workers=1, queue_size=1)
            )
            dialog = ArchiveDirectoryDialog(archive)
            root_item = dialog._tree.topLevelItem(0)
            self.assertEqual(root_item.text(0), ui_text.SNAPSHOT_ROOT)
            self.assertEqual(root_item.child(0).text(0), "nested")
            self.assertEqual(dialog.selected_directory(), "")
            dialog.close()

    def test_snapshot_thread_generates_real_html(self) -> None:
        """桌面快照线程能生成实际 HTML 产物。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "backup.html"
            source.mkdir()
            (source / "sample.txt").write_text("content", encoding="utf-8")
            window = MainWindow()
            window._snapshot_source.setText(str(source))
            window._snapshot_output.setText(str(output))
            window._start_snapshot_from_page()
            deadline = monotonic() + 10
            while window._active_scan_thread.isRunning() and monotonic() < deadline:
                self.application.processEvents()
                window._active_scan_thread.wait(50)
            self.application.processEvents()
            self.assertTrue(output.is_file())
            self.assertFalse(window._result_panel.isHidden())
            window.close()

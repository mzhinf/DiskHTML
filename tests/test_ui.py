"""HTML 快照图形界面测试。"""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from unittest import TestCase
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QCheckBox, QPushButton, QTreeWidget

from diskhtml.config import ScanConfig
from diskhtml.html_archive import create_html_snapshot
from diskhtml.models import ScanProgress
from diskhtml.ui import ArchiveDirectoryDialog, MainWindow


class UiTests(TestCase):
    """验证 GUI 只暴露 HTML 快照和目录对本机目录比较工作流。"""

    @classmethod
    def setUpClass(cls) -> None:
        """创建测试共享的离屏 Qt 应用。"""

        cls.application = QApplication.instance() or QApplication([])

    def test_window_only_exposes_html_workflow_actions(self) -> None:
        """工具栏不应再出现 SQLite 项目和两份 HTML 比较入口。"""

        window = MainWindow()
        labels = {button.text() for button in window.findChildren(QPushButton)}

        self.assertTrue(
            {
                "\u751f\u6210\u5feb\u7167 HTML",
                "\u6bd4\u8f83\u5feb\u7167\u76ee\u5f55",
                "\u4ece SQLite \u751f\u6210\u5feb\u7167 HTML",
                "\u6682\u505c",
                "\u7ee7\u7eed",
                "\u53d6\u6d88",
            }
            <= labels
        )
        self.assertFalse(
            {
                "\u65b0\u5efa\u9879\u76ee",
                "\u6253\u5f00\u9879\u76ee",
                "\u626b\u63cf\u8def\u5f84",
                "\u6062\u590d\u4efb\u52a1",
                "\u6bd4\u8f83 HTML",
                "\u6253\u5f00\u62a5\u544a",
                "\u626b\u63cf\u914d\u7f6e",
            }
            & labels
        )
        self.assertIn("HTML 快照", window.windowTitle())
        window.close()

    def test_scan_progress_updates_status_bar(self) -> None:
        """扫描进度应更新状态栏并显示指示器。"""

        window = MainWindow()
        window._scan_progress(
            ScanProgress("scan-1", 5, 3, 2 * 1024 * 1024, "data/a.bin", 1024 * 1024, 12)
        )
        self.assertIn("3/5", window.statusBar().currentMessage())
        self.assertIn("data/a.bin", window.statusBar().currentMessage())
        self.assertFalse(window._scan_progress_bar.isHidden())
        window.close()

    def test_follow_links_toggle_updates_scan_config(self) -> None:
        """\u8f6f\u94fe\u63a5\u590d\u9009\u6846\u5e94\u540c\u6b65\u66f4\u65b0\u540e\u7eed\u4efb\u52a1\u7684\u626b\u63cf\u914d\u7f6e\u3002"""

        window = MainWindow()
        toggle = window.findChild(QCheckBox)
        self.assertIsNotNone(toggle)
        toggle.setChecked(True)
        self.assertTrue(window._scan_config.follow_links)
        window.close()

    def test_create_snapshot_starts_html_background_thread(self) -> None:
        """选择目录和输出后应创建 HTML 快照后台线程。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            source = Path(directory) / "source"
            source.mkdir()
            output = Path(directory) / "backup.html"
            window = MainWindow()
            with (
                patch("diskhtml.ui.QFileDialog.getExistingDirectory", return_value=str(source)),
                patch("diskhtml.ui.QFileDialog.getSaveFileName", return_value=(str(output), "")),
                patch("diskhtml.ui.HtmlSnapshotThread") as thread_class,
            ):
                window.create_snapshot()
            self.assertEqual(thread_class.call_args.args[:3], (source, output, window._scan_config))
            thread_class.return_value.start.assert_called_once_with()
            window.close()

    def test_start_compare_uses_selected_archive_directory(self) -> None:
        """比较线程应接收 HTML 树中选择的目录和本机目录。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            archive = root / "old.html"
            source = root / "current"
            source.mkdir()
            output = root / "compare.html"
            window = MainWindow()
            with patch("diskhtml.ui.HtmlDirectoryCompareThread") as thread_class:
                window._start_compare(archive, "资料/图片", source, output)
            self.assertEqual(
                thread_class.call_args.args[:5],
                (archive, "资料/图片", source, output, window._scan_config),
            )
            thread_class.return_value.start.assert_called_once_with()
            window.close()

    def test_archive_directory_dialog_renders_html_directory_tree(self) -> None:
        """目录选择对话框应展示 HTML 快照中的层级目录。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "资料").mkdir()
            (source / "资料" / "图片").mkdir()
            (source / "资料" / "图片" / "one.txt").write_text("内容", encoding="utf-8")
            archive = create_html_snapshot(
                source, root / "backup.html", ScanConfig(workers=1, queue_size=1)
            )
            dialog = ArchiveDirectoryDialog(archive)
            tree = dialog.findChild(QTreeWidget)
            root_item = tree.topLevelItem(0)
            child = root_item.child(0)
            self.assertEqual(root_item.text(0), "快照根目录")
            self.assertEqual(child.text(0), "资料")
            self.assertEqual(dialog.selected_directory(), "")
            dialog.close()

    def test_directory_backup_completes_through_background_thread(self) -> None:
        """窗口应通过后台线程生成实际可读取的 HTML 快照。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "backup.html"
            source.mkdir()
            (source / "sample.txt").write_text("内容", encoding="utf-8")
            window = MainWindow()
            window._start_snapshot(source, output)
            deadline = monotonic() + 10
            while window._active_scan_thread.isRunning() and monotonic() < deadline:
                self.application.processEvents()
                window._active_scan_thread.wait(50)
            self.assertFalse(window._active_scan_thread.isRunning())
            self.application.processEvents()
            self.assertTrue(output.is_file())
            self.assertIn("HTML 快照已生成", window.statusBar().currentMessage())
            window.close()

    def test_control_without_running_task_reports_message(self) -> None:
        """没有运行中扫描时，控制按钮应给出明确提示。"""

        window = MainWindow()
        window.pause_active_scan()
        self.assertIn("没有可控制", window.statusBar().currentMessage())
        window.close()

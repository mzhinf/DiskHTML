"""HTML 冷备图形界面测试。"""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from unittest import TestCase
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPushButton, QTreeWidget

from diskhtml.config import ScanConfig
from diskhtml.html_archive import create_html_backup
from diskhtml.models import ScanProgress
from diskhtml.ui import ArchiveDirectoryDialog, MainWindow


class UiTests(TestCase):
    """验证 GUI 只暴露 HTML 冷备和目录对本机目录比较工作流。"""

    @classmethod
    def setUpClass(cls) -> None:
        """创建测试共享的离屏 Qt 应用。"""

        cls.application = QApplication.instance() or QApplication([])

    def test_window_only_exposes_html_workflow_actions(self) -> None:
        """工具栏不应再出现 SQLite 项目和两份 HTML 比较入口。"""

        window = MainWindow()
        labels = {button.text() for button in window.findChildren(QPushButton)}

        self.assertTrue(
            {"生成冷备 HTML", "比较冷备目录", "打开报告", "扫描配置", "暂停", "继续", "取消"}
            <= labels
        )
        self.assertFalse({"新建项目", "打开项目", "扫描路径", "恢复任务", "比较 HTML"} & labels)
        self.assertIn("HTML 冷备", window.windowTitle())
        window.close()

    def test_open_report_uses_system_browser(self) -> None:
        """选择 HTML 报告后应委托系统默认浏览器打开本地文件。"""

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
        """扫描进度应更新状态栏并显示指示器。"""

        window = MainWindow()
        window._scan_progress(
            ScanProgress("scan-1", 5, 3, 2 * 1024 * 1024, "data/a.bin", 1024 * 1024, 12)
        )
        self.assertIn("3/5", window.statusBar().currentMessage())
        self.assertIn("data/a.bin", window.statusBar().currentMessage())
        self.assertFalse(window._scan_progress_bar.isHidden())
        window.close()

    def test_load_scan_config_uses_selected_toml(self) -> None:
        """选择配置文件后应使用其中的扫描与排除规则。"""

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
            window.close()

    def test_create_backup_starts_html_background_thread(self) -> None:
        """选择目录和输出后应创建 HTML 冷备后台线程。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            source = Path(directory) / "source"
            source.mkdir()
            output = Path(directory) / "backup.html"
            window = MainWindow()
            with (
                patch("diskhtml.ui.QFileDialog.getExistingDirectory", return_value=str(source)),
                patch("diskhtml.ui.QFileDialog.getSaveFileName", return_value=(str(output), "")),
                patch("diskhtml.ui.HtmlBackupThread") as thread_class,
            ):
                window.create_backup()
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
        """目录选择对话框应展示 HTML 冷备中的层级目录。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "资料").mkdir()
            (source / "资料" / "图片").mkdir()
            (source / "资料" / "图片" / "one.txt").write_text("内容", encoding="utf-8")
            archive = create_html_backup(
                source, root / "backup.html", ScanConfig(workers=1, queue_size=1)
            )
            dialog = ArchiveDirectoryDialog(archive)
            tree = dialog.findChild(QTreeWidget)
            root_item = tree.topLevelItem(0)
            child = root_item.child(0)
            self.assertEqual(root_item.text(0), "冷备根目录")
            self.assertEqual(child.text(0), "资料")
            self.assertEqual(dialog.selected_directory(), "")
            dialog.close()

    def test_directory_backup_completes_through_background_thread(self) -> None:
        """窗口应通过后台线程生成实际可读取的 HTML 冷备。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "backup.html"
            source.mkdir()
            (source / "sample.txt").write_text("内容", encoding="utf-8")
            window = MainWindow()
            window._start_backup(source, output)
            deadline = monotonic() + 10
            while window._active_scan_thread.isRunning() and monotonic() < deadline:
                self.application.processEvents()
                window._active_scan_thread.wait(50)
            self.assertFalse(window._active_scan_thread.isRunning())
            self.application.processEvents()
            self.assertTrue(output.is_file())
            self.assertIn("HTML 冷备已生成", window.statusBar().currentMessage())
            window.close()

    def test_control_without_running_task_reports_message(self) -> None:
        """没有运行中扫描时，控制按钮应给出明确提示。"""

        window = MainWindow()
        window.pause_active_scan()
        self.assertIn("没有可控制", window.statusBar().currentMessage())
        window.close()

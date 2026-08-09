"""DiskHTML Tkinter 桌面生成界面测试。"""

from __future__ import annotations

import queue
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from unittest import TestCase
from unittest.mock import patch

from diskhtml import __version__, ui_text
from diskhtml.config import HashMode, ScanConfig
from diskhtml.html_archive import create_html_snapshot, sqlite_snapshot_path
from diskhtml.models import ScanProgress
from diskhtml.ui import ArchiveDirectoryDialog, MainWindow


class UiTests(TestCase):
    """验证三页签输入、内联校验和后台任务桥接。"""

    def setUp(self) -> None:
        """每项测试开始前重置默认语言并创建隐藏窗口。"""

        ui_text.set_language("zh-CN")
        self.window = MainWindow()
        self.window.withdraw()
        self.window.update_idletasks()

    def tearDown(self) -> None:
        """销毁 Tk 根窗口，避免不同测试共享事件队列。"""

        if self.window.winfo_exists():
            self.window._close_window()

    def test_window_has_three_task_tabs_and_hidden_runtime_panels(self) -> None:
        """窗口只显示三个任务页，运行与结果区域初始隐藏。"""

        tabs = self.window._tabs.tabs()
        self.assertEqual(
            [self.window._tabs.tab(tab, "text") for tab in tabs],
            [ui_text.TAB_SNAPSHOT, ui_text.TAB_COMPARE, ui_text.TAB_SQLITE],
        )
        self.assertEqual("", self.window._run_panel.winfo_manager())
        self.assertEqual("", self.window._result_panel.winfo_manager())
        self.assertEqual((920, 900), (self.window.winfo_width(), self.window.winfo_height()))
        self.assertEqual((920, 900), (self.window.minsize()[0], self.window.minsize()[1]))
        self.assertEqual(self.window.minsize(), self.window.maxsize())
        self.assertTrue(all(self.window._tabs.tab(tab, "image") for tab in tabs))

    def test_fixed_window_contains_worst_case_task_layout(self) -> None:
        """采样选项、错误提示和运行区展开后仍应留有安全边距。"""

        safety_margin = 24
        self.window._snapshot_hash_mode_var.set(HashMode.SAMPLED.value)
        self.window._refresh_snapshot_hash_controls()
        self.window._set_error(self.window._snapshot_source_error, "源目录错误提示占位")
        self.window._set_error(self.window._snapshot_output_error, "输出路径错误提示占位")
        self.window._set_error(self.window._snapshot_hash_error, "采样参数错误提示占位")
        self.window._run_panel.pack(fill="x", pady=(10, 0))
        self.window.update_idletasks()

        required = (self.window.winfo_reqwidth(), self.window.winfo_reqheight())
        available = (self.window.winfo_width(), self.window.winfo_height())
        self.assertLessEqual(required[0] + safety_margin, available[0])
        self.assertLessEqual(required[1] + safety_margin, available[1])

    def test_language_switch_preserves_form_values(self) -> None:
        """切换中英文时保留路径、开关和当前任务页。"""

        self.window._snapshot_source_var.set("D:/source")
        self.window._snapshot_output_var.set("D:/snapshot.html")
        self.window._snapshot_follow_var.set(True)
        self.window._snapshot_hash_mode_var.set(HashMode.SAMPLED.value)
        self.window._snapshot_sample_target_mb_var.set("16")
        self.window._snapshot_sample_count_var.set("12")
        self.window._tabs.select(1)
        self.window._language_selector.current(self.window._language_codes.index("en"))
        self.window._change_language()

        self.assertEqual("en", ui_text.current_language())
        self.assertEqual(f"DiskHTML - HTML Snapshot Generator v{__version__}", self.window.title())
        self.assertEqual("Create Snapshot", self.window._tabs.tab(0, "text"))
        self.assertEqual(1, self.window._tabs.index(self.window._tabs.select()))
        self.assertEqual("D:/source", self.window._snapshot_source_var.get())
        self.assertEqual("D:/snapshot.html", self.window._snapshot_output_var.get())
        self.assertTrue(self.window._snapshot_follow_var.get())
        self.assertEqual(HashMode.SAMPLED.value, self.window._snapshot_hash_mode_var.get())
        self.assertEqual("16", self.window._snapshot_sample_target_mb_var.get())
        self.assertEqual("12", self.window._snapshot_sample_count_var.get())
        self.assertEqual("Language", self.window._language_label.cget("text"))

    def test_invalid_compare_inputs_show_inline_errors(self) -> None:
        """比对页无效输入必须在对应字段下显示错误。"""

        self.window._compare_archive_var.set("Z:/missing.html")
        self.window._compare_source_var.set("Z:/missing-directory")
        self.window._compare_output_var.set("Z:/missing/report.html")
        self.window._start_compare_from_page()

        for label in (
            self.window._compare_archive_error,
            self.window._compare_source_error,
            self.window._compare_output_error,
        ):
            self.assertTrue(label.cget("text"))
            self.assertEqual("pack", label.winfo_manager())

    def test_sampled_controls_show_warning_and_validate_parameters(self) -> None:
        """采样配置仅在采样模式显示，并阻止无效目标读取量进入任务。"""

        self.assertEqual("", self.window._snapshot_sample_frame.winfo_manager())
        self.window._snapshot_hash_mode_var.set(HashMode.SAMPLED.value)
        self.window._refresh_snapshot_hash_controls()
        self.assertEqual("pack", self.window._snapshot_sample_frame.winfo_manager())
        self.assertEqual("pack", self.window._snapshot_hash_warning.winfo_manager())

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            self.window._snapshot_source_var.set(str(source))
            self.window._snapshot_output_var.set(str(root / "snapshot.html"))
            self.window._snapshot_sample_target_mb_var.set("0")
            self.window._start_snapshot_from_page()

        self.assertTrue(self.window._snapshot_hash_error.cget("text"))

    def test_snapshot_output_suggestion_includes_short_date(self) -> None:
        """源目录变更后自动建议带短日期的 HTML 和 SQLite 文件名。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "documents"
            source.mkdir()
            self.window._snapshot_source_var.set(str(source))
            output = root / f"documents_{date.today():%y-%m-%d}.html"
            self.assertEqual(str(output), self.window._snapshot_output_var.get())
            self.assertEqual(
                f"documents_{date.today():%y-%m-%d}.sqlite3",
                sqlite_snapshot_path(output).name,
            )

    def test_snapshot_page_starts_background_task_with_follow_links(self) -> None:
        """快照页将输入、输出和软链接选项传给后台任务。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            output = root / "snapshot.html"
            self.window._snapshot_source_var.set(str(source))
            self.window._snapshot_output_var.set(str(output))
            self.window._snapshot_follow_var.set(True)
            self.window._snapshot_hash_mode_var.set(HashMode.SAMPLED.value)
            self.window._snapshot_sample_target_mb_var.set("16")
            self.window._snapshot_sample_count_var.set("4")
            with patch("diskhtml.ui.HtmlSnapshotThread") as task_class:
                task = task_class.return_value
                task.events = queue.Queue()
                task.is_alive.return_value = True
                self.window._start_snapshot_from_page()

            args = task_class.call_args.args
            self.assertEqual((source, output), args[:2])
            self.assertTrue(args[2].follow_links)
            self.assertEqual(HashMode.SAMPLED, args[2].hash_mode)
            self.assertEqual(16 * 1024 * 1024, args[2].sample_target_bytes)
            self.assertEqual(4, args[2].sample_count)
            task.start.assert_called_once_with()
            self.assertEqual("pack", self.window._run_panel.winfo_manager())
            self.assertEqual("disabled", str(self.window._language_selector.cget("state")))

    def test_compare_page_starts_task_with_selected_directory(self) -> None:
        """比对页将基准快照子目录与本机目录传给后台任务。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            archive = root / "old.html"
            archive.write_text("placeholder", encoding="utf-8")
            source = root / "current"
            source.mkdir()
            output = root / "compare.html"
            self.window._compare_archive_var.set(str(archive))
            self.window._compare_source_var.set(str(source))
            self.window._compare_output_var.set(str(output))
            self.window._compare_archive_directory = "folder/photos"
            with (
                patch("diskhtml.ui.html_snapshot_directories", return_value=("", "folder/photos")),
                patch(
                    "diskhtml.ui.html_snapshot_scan_config",
                    return_value=ScanConfig(hash_mode=HashMode.SAMPLED),
                ),
                patch("diskhtml.ui.HtmlDirectoryCompareThread") as task_class,
            ):
                task = task_class.return_value
                task.events = queue.Queue()
                task.is_alive.return_value = True
                self.window._start_compare_from_page()

            args = task_class.call_args.args
            self.assertEqual((archive, "folder/photos", source, output), args[:4])
            self.assertEqual(HashMode.SAMPLED, args[4].hash_mode)
            task.start.assert_called_once_with()

    def test_progress_and_completion_use_dedicated_panels(self) -> None:
        """扫描进度和生成结果显示在各自区域。"""

        self.window._run_panel.pack()
        self.window._scan_progress(
            ScanProgress("scan-1", 5, 3, 2 * 1024 * 1024, "data/a.bin", 1024 * 1024, 12)
        )
        self.assertIn("3/5", self.window._run_files_var.get())
        self.assertIn("data/a.bin", self.window._run_path_var.get())
        self.window._snapshot_completed("C:/result.html")
        self.assertEqual("", self.window._run_panel.winfo_manager())
        self.assertEqual("pack", self.window._result_panel.winfo_manager())
        self.assertIn("C:/result.html", self.window._result_message_var.get())

    def test_archive_directory_dialog_renders_directory_tree(self) -> None:
        """快照目录选择对话框保留目录层级和根目录语义。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "nested").mkdir()
            (source / "nested" / "one.txt").write_text("content", encoding="utf-8")
            archive = create_html_snapshot(
                source, root / "backup.html", ScanConfig(workers=1, queue_size=1)
            )
            dialog = ArchiveDirectoryDialog(archive, self.window)
            dialog.withdraw()
            root_item = dialog._tree.get_children("")[0]
            nested = dialog._tree.get_children(root_item)[0]
            self.assertEqual(ui_text.SNAPSHOT_ROOT, dialog._tree.item(root_item, "text"))
            self.assertEqual("nested", dialog._tree.item(nested, "text"))
            self.assertEqual("", dialog.selected_directory())
            dialog.destroy()

    def test_snapshot_background_task_generates_real_html(self) -> None:
        """Tk 事件队列能够接收真实后台扫描完成事件。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "backup.html"
            source.mkdir()
            (source / "sample.txt").write_text("content", encoding="utf-8")
            self.window._snapshot_source_var.set(str(source))
            self.window._snapshot_output_var.set(str(output))
            self.window._start_snapshot_from_page()
            deadline = monotonic() + 30
            while monotonic() < deadline:
                self.window.update()
                task = self.window._active_scan_thread
                if task is not None:
                    task.wait(20)
                if output.is_file() and self.window._result_panel.winfo_manager() == "pack":
                    break
            self.assertTrue(output.is_file())
            self.assertEqual("pack", self.window._result_panel.winfo_manager())

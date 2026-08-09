"""DiskHTML 的 Tkinter/ttk HTML 快照桌面生成界面。"""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path
from tkinter import filedialog, ttk

from . import ui_text
from .config import HashMode, ScanConfig
from .html_archive import (
    compare_html_directory_to_source,
    create_html_snapshot,
    html_snapshot_directories,
    html_snapshot_scan_config,
    render_html_snapshot_from_sqlite,
)
from .models import ScanProgress
from .sampled_hash import MAX_SAMPLE_COUNT
from .scanner import ScanController
from .version import __version__

TaskEvent = tuple[str, object]
_MEBIBYTE = 1024 * 1024


def _hash_strategy_label(config: ScanConfig) -> str:
    """返回 GUI 中展示的请求 Hash 策略名称和稳定标识。"""

    label = (
        ui_text.HASH_MODE_SAMPLED
        if config.hash_mode is HashMode.SAMPLED
        else ui_text.HASH_MODE_FULL
    )
    return f"{label} ({config.requested_hash_algorithm()})"


def _asset_path(name: str) -> Path:
    """返回源码运行和 PyInstaller 运行时均可读取的资源路径。"""

    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "diskhtml" / "assets" / name  # type: ignore[attr-defined]
    return Path(__file__).with_name("assets") / name


class BackgroundTask:
    """在线程中执行任务，并通过队列向 Tk 主线程发送事件。"""

    def __init__(self) -> None:
        self.events: queue.Queue[TaskEvent] = queue.Queue()
        self._thread: threading.Thread | None = None

    def _emit(self, event: str, value: object) -> None:
        """写入一个线程安全的任务事件。"""

        self.events.put((event, value))

    def start(self) -> None:
        """启动后台线程。"""

        if self.is_alive():
            raise RuntimeError("任务已经在运行。")
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def run(self) -> None:
        """由具体任务实现后台工作。"""

        raise NotImplementedError

    def is_alive(self) -> bool:
        """返回后台线程是否仍在运行。"""

        return self._thread is not None and self._thread.is_alive()

    def wait(self, timeout_ms: int | None = None) -> bool:
        """等待任务结束，并返回任务是否已结束。"""

        if self._thread is None:
            return True
        timeout = None if timeout_ms is None else timeout_ms / 1000
        self._thread.join(timeout)
        return not self._thread.is_alive()


class HtmlSnapshotThread(BackgroundTask):
    """在后台生成目录快照 HTML。"""

    def __init__(
        self, source: Path, output: Path, config: ScanConfig, controller: ScanController
    ) -> None:
        super().__init__()
        self.source = source
        self.output = output
        self.config = config
        self.controller = controller

    def run(self) -> None:
        """执行扫描并生成快照文件。"""

        try:
            output = create_html_snapshot(
                self.source,
                self.output,
                self.config,
                lambda progress: self._emit("progress", progress),
                self.controller,
            )
            self._emit("completed", str(output))
        except (OSError, RuntimeError, ValueError) as exc:
            self._emit("failed", str(exc))


class SqliteHtmlRenderThread(BackgroundTask):
    """从 SQLite 快照索引后台生成 HTML。"""

    def __init__(self, database: Path, output: Path) -> None:
        super().__init__()
        self.database = database
        self.output = output

    def run(self) -> None:
        """执行离线 HTML 渲染。"""

        try:
            output = render_html_snapshot_from_sqlite(self.database, self.output)
            self._emit("completed", str(output))
        except (OSError, RuntimeError, ValueError) as exc:
            self._emit("failed", str(exc))


class HtmlDirectoryCompareThread(BackgroundTask):
    """在后台比较 HTML 快照与本机目录。"""

    def __init__(
        self,
        archive: Path,
        archived_directory: str,
        source: Path,
        output: Path,
        config: ScanConfig,
        controller: ScanController,
    ) -> None:
        super().__init__()
        self.archive = archive
        self.archived_directory = archived_directory
        self.source = source
        self.output = output
        self.config = config
        self.controller = controller

    def run(self) -> None:
        """执行目录比较并生成报告 HTML。"""

        try:
            output = compare_html_directory_to_source(
                self.archive,
                self.archived_directory,
                self.source,
                self.output,
                self.config,
                lambda progress: self._emit("progress", progress),
                self.controller,
            )
            self._emit("completed", str(output))
        except (OSError, RuntimeError, ValueError) as exc:
            self._emit("failed", str(exc))


class ArchiveDirectoryDialog(tk.Toplevel):
    """选择快照内目录的树形对话框。"""

    def __init__(self, archive: Path, parent: tk.Misc | None = None) -> None:
        super().__init__(parent)
        self.title(ui_text.SELECT_ARCHIVED_DIRECTORY)
        self.geometry("560x430")
        self.minsize(480, 340)
        self._accepted = False
        self.transient(parent)
        container = ttk.Frame(self, padding=12)
        container.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            container,
            text=f"{ui_text.BASELINE_SNAPSHOT} - {archive.name}",
            style="FieldTitle.TLabel",
        ).pack(fill=tk.X, pady=(0, 8))
        tree_frame = ttk.Frame(container)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        self._tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse")
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._build_tree(html_snapshot_directories(archive))
        buttons = ttk.Frame(container)
        buttons.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(buttons, text=ui_text.CANCEL, command=self._cancel).pack(side=tk.RIGHT)
        ttk.Button(buttons, text=ui_text.CONFIRM, command=self._confirm).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _build_tree(self, directories: tuple[str, ...]) -> None:
        """根据目录路径构建选择树。"""

        root = self._tree.insert("", tk.END, text=ui_text.SNAPSHOT_ROOT, values=("",), open=True)
        items = {"": root}
        for directory in directories:
            if not directory:
                continue
            parent_path = ""
            for part in directory.split("/"):
                current_path = f"{parent_path}/{part}".strip("/")
                if current_path not in items:
                    items[current_path] = self._tree.insert(
                        items[parent_path], tk.END, text=part, values=(current_path,)
                    )
                parent_path = current_path
        self._tree.selection_set(root)
        self._tree.focus(root)

    def selected_directory(self) -> str | None:
        """返回当前选择的快照内目录。"""

        selection = self._tree.selection()
        if not selection:
            return None
        values = self._tree.item(selection[0], "values")
        return str(values[0]) if values else ""

    def _confirm(self) -> None:
        """接受当前目录选择。"""

        self._accepted = True
        self.destroy()

    def _cancel(self) -> None:
        """取消目录选择。"""

        self._accepted = False
        self.destroy()

    def show_modal(self) -> bool:
        """显示模态对话框并返回是否确认。"""

        self.grab_set()
        self.wait_window()
        return self._accepted


def _window_title() -> str:
    """返回包含当前产品版本的桌面窗口标题。"""

    return f"{ui_text.WINDOW_TITLE} v{__version__}"


class MainWindow(tk.Tk):
    """只负责配置并执行 HTML 生成任务的主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.title(_window_title())
        self.geometry("920x900")
        self.resizable(False, False)
        self.minsize(920, 900)
        self.maxsize(920, 900)
        icon = _asset_path("folder-tree.ico")
        if icon.is_file():
            try:
                self.iconbitmap(default=str(icon))
            except tk.TclError:
                pass
        self._scan_config = ScanConfig()
        self._compare_archive_directory = ""
        self._last_output: Path | None = None
        self._active_scan_thread: BackgroundTask | None = None
        self._active_scan_controller: ScanController | None = None
        self._completion_handler: Callable[[str], None] | None = None
        self._status_reset_after: str | None = None
        self._task_poll_after: str | None = None
        self._tab_images: list[tk.PhotoImage] = []
        self._configure_styles()
        self._setup_language_selector()
        self._setup_central_content()
        self._show_status(ui_text.READY)
        self.protocol("WM_DELETE_WINDOW", self._close_window)

    def _configure_styles(self) -> None:
        """配置紧凑的 Windows 桌面工具样式。"""

        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("App.TFrame", background="#f5f6f7")
        style.configure("Page.TFrame", background="#ffffff")
        style.configure("Heading.TLabel", background="#ffffff", font=("Segoe UI", 16, "bold"))
        style.configure("Description.TLabel", background="#ffffff", foreground="#68737d")
        style.configure("FieldTitle.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Error.TLabel", foreground="#bb2424")
        style.configure("Warning.TLabel", foreground="#8a5500")
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(18, 7))
        style.configure("Task.TLabelframe", padding=10)
        style.configure("TNotebook.Tab", padding=(18, 9), font=("Segoe UI", 10))

    def _setup_language_selector(self) -> None:
        """创建底部状态栏和语言选择控件。"""

        self._status_frame = ttk.Frame(self, padding=(10, 5))
        self._status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self._status_var = tk.StringVar()
        ttk.Label(self._status_frame, textvariable=self._status_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        self._language_label = ttk.Label(self._status_frame)
        self._language_label.pack(side=tk.LEFT, padx=(8, 5))
        self._language_selector = ttk.Combobox(self._status_frame, state="readonly", width=12)
        self._language_selector.pack(side=tk.LEFT)
        self._language_selector.bind("<<ComboboxSelected>>", self._change_language)
        self._refresh_language_selector()

    def _refresh_language_selector(self) -> None:
        """按当前语言刷新语言选择控件。"""

        languages = ui_text.supported_languages()
        self._language_codes = [code for code, _label in languages]
        self._language_label.configure(text=ui_text.LANGUAGE)
        self._language_selector.configure(values=[label for _code, label in languages])
        self._language_selector.current(self._language_codes.index(ui_text.current_language()))

    def _capture_form_values(self) -> dict[str, object]:
        """保存语言重建前的路径、开关和当前任务页。"""

        return {
            "snapshot_source": self._snapshot_source_var.get(),
            "snapshot_output": self._snapshot_output_var.get(),
            "snapshot_follow": self._snapshot_follow_var.get(),
            "snapshot_hash_mode": self._snapshot_hash_mode_var.get(),
            "snapshot_sample_budget_mb": self._snapshot_sample_budget_mb_var.get(),
            "snapshot_sample_count": self._snapshot_sample_count_var.get(),
            "compare_archive": self._compare_archive_var.get(),
            "compare_source": self._compare_source_var.get(),
            "compare_output": self._compare_output_var.get(),
            "compare_follow": self._compare_follow_var.get(),
            "compare_archive_directory": self._compare_archive_directory,
            "sqlite_database": self._sqlite_database_var.get(),
            "sqlite_output": self._sqlite_output_var.get(),
            "tab_index": self._tabs.index(self._tabs.select()),
        }

    def _restore_form_values(self, values: dict[str, object]) -> None:
        """恢复语言重建后的路径、开关、快照子目录和任务页。"""

        self._snapshot_source_var.set(str(values["snapshot_source"]))
        self._snapshot_output_var.set(str(values["snapshot_output"]))
        self._snapshot_follow_var.set(bool(values["snapshot_follow"]))
        self._snapshot_hash_mode_var.set(str(values["snapshot_hash_mode"]))
        self._snapshot_sample_budget_mb_var.set(str(values["snapshot_sample_budget_mb"]))
        self._snapshot_sample_count_var.set(str(values["snapshot_sample_count"]))
        self._refresh_snapshot_hash_controls()
        self._compare_archive_var.set(str(values["compare_archive"]))
        self._compare_source_var.set(str(values["compare_source"]))
        self._compare_output_var.set(str(values["compare_output"]))
        self._compare_follow_var.set(bool(values["compare_follow"]))
        self._compare_archive_directory = str(values["compare_archive_directory"])
        selected = self._compare_archive_directory or ui_text.SNAPSHOT_ROOT
        self._compare_directory_var.set(f"{ui_text.SNAPSHOT_DIRECTORY}: {selected}")
        self._sqlite_database_var.set(str(values["sqlite_database"]))
        self._sqlite_output_var.set(str(values["sqlite_output"]))
        self._tabs.select(int(values["tab_index"]))

    def _change_language(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        """切换界面语言，同时保留未提交的表单输入。"""

        index = self._language_selector.current()
        if index < 0 or self._active_scan_running():
            return
        language = self._language_codes[index]
        if language == ui_text.current_language():
            return
        values = self._capture_form_values()
        ui_text.set_language(language)
        self.title(_window_title())
        self._setup_central_content()
        self._restore_form_values(values)
        self._refresh_language_selector()
        self._show_status(ui_text.READY)

    def _setup_central_content(self) -> None:
        """构建任务页签及共享运行区域。"""

        previous = getattr(self, "_content", None)
        if previous is not None:
            previous.destroy()
        self._content = ttk.Frame(self, style="App.TFrame", padding=(24, 16, 24, 12))
        self._content.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._tabs = ttk.Notebook(self._content)
        self._tabs.pack(fill=tk.BOTH, expand=True)
        pages = (
            (self._build_snapshot_page(), "folders.png", ui_text.TAB_SNAPSHOT),
            (self._build_compare_page(), "git-compare.png", ui_text.TAB_COMPARE),
            (self._build_sqlite_page(), "database.png", ui_text.TAB_SQLITE),
        )
        self._tab_images = []
        for page, image_name, label in pages:
            options: dict[str, object] = {"text": label, "compound": tk.LEFT}
            image_path = _asset_path(image_name)
            if image_path.is_file():
                try:
                    photo = tk.PhotoImage(file=str(image_path))
                    self._tab_images.append(photo)
                    options["image"] = photo
                except tk.TclError:
                    pass
            self._tabs.add(page, **options)
        self._run_panel = self._build_run_panel(self._content)
        self._result_panel = self._build_result_panel(self._content)

    def _page_frame(self, heading: str, description: str) -> tk.Frame:
        """创建带标题与说明的任务页面。"""

        page = ttk.Frame(self._tabs, style="Page.TFrame", padding=(20, 18, 20, 20))
        ttk.Label(page, text=heading, style="Heading.TLabel").pack(anchor=tk.W)
        ttk.Label(page, text=description, style="Description.TLabel").pack(
            anchor=tk.W, pady=(4, 14)
        )
        return page

    def _field(
        self,
        page: tk.Misc,
        variable: tk.StringVar,
        label: str,
        description: str,
        button_label: str,
        callback: Callable[[], None],
    ) -> tuple[ttk.Entry, ttk.Label]:
        """创建路径输入字段及其校验提示。"""

        frame = ttk.Frame(page, style="Page.TFrame")
        frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(frame, text=label, style="FieldTitle.TLabel", background="#ffffff").pack(
            anchor=tk.W
        )
        row = ttk.Frame(frame, style="Page.TFrame")
        row.pack(fill=tk.X, pady=(4, 2))
        edit = ttk.Entry(row, textvariable=variable)
        edit.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
        ttk.Button(row, text=button_label, command=callback, width=16).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Label(frame, text=description, style="Description.TLabel", wraplength=780).pack(
            anchor=tk.W
        )
        error = ttk.Label(frame, text="", style="Error.TLabel", background="#ffffff")
        return edit, error

    def _primary_button(self, page: tk.Misc, text: str, command: Callable[[], None]) -> None:
        """在任务页底部创建主要操作按钮。"""

        ttk.Button(page, text=text, command=command, style="Primary.TButton").pack(
            side=tk.BOTTOM, anchor=tk.E, pady=(10, 0)
        )

    def _build_snapshot_page(self) -> tk.Frame:
        """构建生成目录快照任务页。"""

        page = self._page_frame(ui_text.SNAPSHOT_HEADING, ui_text.SNAPSHOT_DESCRIPTION)
        self._snapshot_source_var = tk.StringVar()
        self._snapshot_output_var = tk.StringVar()
        self._snapshot_follow_var = tk.BooleanVar(value=self._scan_config.follow_links)
        self._snapshot_source, self._snapshot_source_error = self._field(
            page,
            self._snapshot_source_var,
            ui_text.SOURCE_DIRECTORY,
            ui_text.SNAPSHOT_SOURCE_HELP,
            ui_text.SELECT_DIRECTORY,
            self._choose_snapshot_source,
        )
        self._snapshot_output, self._snapshot_output_error = self._field(
            page,
            self._snapshot_output_var,
            ui_text.OUTPUT_HTML,
            ui_text.SNAPSHOT_OUTPUT_HELP,
            ui_text.CHANGE_LOCATION,
            self._choose_snapshot_output,
        )
        self._snapshot_source_var.trace_add("write", self._suggest_snapshot_output)
        hash_frame = ttk.LabelFrame(page, text=ui_text.HASH_STRATEGY, padding=(10, 6))
        hash_frame.pack(fill=tk.X, pady=(2, 6))
        self._snapshot_hash_mode_var = tk.StringVar(value=self._scan_config.hash_mode.value)
        self._snapshot_sample_budget_mb_var = tk.StringVar(
            value=str(self._scan_config.sample_budget // _MEBIBYTE)
        )
        self._snapshot_sample_count_var = tk.StringVar(value=str(self._scan_config.sample_count))
        mode_row = ttk.Frame(hash_frame)
        mode_row.pack(fill=tk.X)
        ttk.Radiobutton(
            mode_row,
            text=ui_text.HASH_MODE_FULL,
            variable=self._snapshot_hash_mode_var,
            value=HashMode.FULL.value,
            command=self._refresh_snapshot_hash_controls,
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            mode_row,
            text=ui_text.HASH_MODE_SAMPLED,
            variable=self._snapshot_hash_mode_var,
            value=HashMode.SAMPLED.value,
            command=self._refresh_snapshot_hash_controls,
        ).pack(side=tk.LEFT, padx=(18, 0))
        self._snapshot_sample_frame = ttk.Frame(hash_frame)
        ttk.Label(self._snapshot_sample_frame, text=ui_text.SAMPLE_BUDGET_MB).pack(side=tk.LEFT)
        ttk.Entry(
            self._snapshot_sample_frame,
            textvariable=self._snapshot_sample_budget_mb_var,
            width=8,
        ).pack(side=tk.LEFT, padx=(6, 16))
        ttk.Label(self._snapshot_sample_frame, text=ui_text.SAMPLE_COUNT).pack(side=tk.LEFT)
        ttk.Spinbox(
            self._snapshot_sample_frame,
            from_=2,
            to=MAX_SAMPLE_COUNT,
            textvariable=self._snapshot_sample_count_var,
            width=6,
        ).pack(side=tk.LEFT, padx=(6, 0))
        self._snapshot_hash_warning = ttk.Label(
            hash_frame, text=ui_text.SAMPLE_WARNING, style="Warning.TLabel"
        )
        self._snapshot_hash_error = ttk.Label(hash_frame, text="", style="Error.TLabel")
        self._refresh_snapshot_hash_controls()
        ttk.Checkbutton(page, text=ui_text.FOLLOW_LINKS, variable=self._snapshot_follow_var).pack(
            anchor=tk.W, pady=(2, 0)
        )
        self._primary_button(page, ui_text.CREATE_SNAPSHOT, self._start_snapshot_from_page)
        return page

    def _refresh_snapshot_hash_controls(self) -> None:
        """只在采样模式下显示预算、次数和快速预检提示。"""

        sampled = self._snapshot_hash_mode_var.get() == HashMode.SAMPLED.value
        if sampled:
            self._snapshot_sample_frame.pack(fill=tk.X, pady=(6, 0))
            self._snapshot_hash_warning.pack(anchor=tk.W, pady=(4, 0))
        else:
            self._snapshot_sample_frame.pack_forget()
            self._snapshot_hash_warning.pack_forget()
            self._set_error(self._snapshot_hash_error, "")

    def _build_compare_page(self) -> tk.Frame:
        """构建生成比对报告任务页。"""

        page = self._page_frame(ui_text.COMPARE_HEADING, ui_text.COMPARE_DESCRIPTION)
        self._compare_archive_var = tk.StringVar()
        self._compare_source_var = tk.StringVar()
        self._compare_output_var = tk.StringVar()
        self._compare_follow_var = tk.BooleanVar(value=self._scan_config.follow_links)
        self._compare_hash_strategy_var = tk.StringVar(value=ui_text.HTML_HASH_PENDING)
        self._compare_directory_var = tk.StringVar(
            value=f"{ui_text.SNAPSHOT_DIRECTORY}: {ui_text.SNAPSHOT_ROOT}"
        )
        self._compare_archive, self._compare_archive_error = self._field(
            page,
            self._compare_archive_var,
            ui_text.BASELINE_SNAPSHOT,
            ui_text.ARCHIVE_HELP,
            ui_text.SELECT_SNAPSHOT,
            self._choose_compare_archive,
        )
        strategy_frame = ttk.LabelFrame(page, text=ui_text.HTML_HASH_STRATEGY, padding=(10, 6))
        strategy_frame.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(strategy_frame, textvariable=self._compare_hash_strategy_var).pack(anchor=tk.W)
        self._compare_source, self._compare_source_error = self._field(
            page,
            self._compare_source_var,
            ui_text.CHECK_DIRECTORY,
            ui_text.CHECK_DIRECTORY_HELP,
            ui_text.SELECT_DIRECTORY,
            self._choose_compare_source,
        )
        directory_row = ttk.Frame(page, style="Page.TFrame")
        directory_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            directory_row, textvariable=self._compare_directory_var, background="#ffffff"
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            directory_row,
            text=ui_text.SELECT_ARCHIVED_DIRECTORY,
            command=self._choose_archived_directory,
            width=20,
        ).pack(side=tk.RIGHT)
        self._compare_output, self._compare_output_error = self._field(
            page,
            self._compare_output_var,
            ui_text.OUTPUT_REPORT,
            ui_text.COMPARE_OUTPUT_HELP,
            ui_text.CHANGE_LOCATION,
            self._choose_compare_output,
        )
        self._compare_archive_var.trace_add("write", self._archive_changed)
        self._compare_source_var.trace_add("write", self._suggest_compare_output)
        ttk.Checkbutton(page, text=ui_text.FOLLOW_LINKS, variable=self._compare_follow_var).pack(
            anchor=tk.W, pady=(2, 0)
        )
        self._primary_button(page, ui_text.CREATE_COMPARE, self._start_compare_from_page)
        return page

    def _build_sqlite_page(self) -> tk.Frame:
        """构建从 SQLite 生成 HTML 的任务页。"""

        page = self._page_frame(ui_text.SQLITE_HEADING, ui_text.SQLITE_DESCRIPTION)
        self._sqlite_database_var = tk.StringVar()
        self._sqlite_output_var = tk.StringVar()
        self._sqlite_database, self._sqlite_database_error = self._field(
            page,
            self._sqlite_database_var,
            ui_text.SQLITE_INDEX,
            ui_text.SQLITE_HELP,
            ui_text.SELECT_SQLITE,
            self._choose_sqlite_database,
        )
        self._sqlite_output, self._sqlite_output_error = self._field(
            page,
            self._sqlite_output_var,
            ui_text.OUTPUT_HTML,
            ui_text.SQLITE_OUTPUT_HELP,
            ui_text.CHANGE_LOCATION,
            self._choose_sqlite_output,
        )
        self._sqlite_database_var.trace_add("write", self._suggest_sqlite_output)
        self._primary_button(page, ui_text.CREATE_SQLITE, self._start_sqlite_from_page)
        return page

    def _build_run_panel(self, parent: tk.Misc) -> ttk.LabelFrame:
        """构建任务运行状态区域。"""

        panel = ttk.LabelFrame(parent, text=ui_text.CURRENT_STAGE, style="Task.TLabelframe")
        self._run_stage_var = tk.StringVar()
        self._run_path_var = tk.StringVar()
        self._run_files_var = tk.StringVar()
        self._run_hash_var = tk.StringVar()
        for variable in (
            self._run_stage_var,
            self._run_path_var,
            self._run_files_var,
            self._run_hash_var,
        ):
            ttk.Label(panel, textvariable=variable).pack(anchor=tk.W, fill=tk.X)
        self._run_progress = ttk.Progressbar(panel, mode="indeterminate")
        self._run_progress.pack(fill=tk.X, pady=(7, 7))
        controls = ttk.Frame(panel)
        controls.pack(fill=tk.X)
        self._pause_button = ttk.Button(
            controls, text=ui_text.PAUSE, command=self.pause_active_scan
        )
        self._resume_button = ttk.Button(
            controls, text=ui_text.RESUME, command=self.resume_active_scan
        )
        self._cancel_button = ttk.Button(
            controls, text=ui_text.CANCEL, command=self.cancel_active_scan
        )
        for button in (self._pause_button, self._resume_button, self._cancel_button):
            button.pack(side=tk.LEFT, padx=(0, 6))
        return panel

    def _build_result_panel(self, parent: tk.Misc) -> ttk.LabelFrame:
        """构建任务完成后的输出操作区域。"""

        panel = ttk.LabelFrame(parent, text=ui_text.SUCCESS, style="Task.TLabelframe")
        self._result_message_var = tk.StringVar()
        ttk.Entry(panel, textvariable=self._result_message_var, state="readonly").pack(
            side=tk.LEFT, fill=tk.X, expand=True, ipady=4
        )
        ttk.Button(panel, text=ui_text.OPEN_HTML, command=self._open_output).pack(
            side=tk.LEFT, padx=(8, 4)
        )
        ttk.Button(panel, text=ui_text.OPEN_FOLDER, command=self._open_output_folder).pack(
            side=tk.LEFT
        )
        return panel

    def _choose_snapshot_source(self) -> None:
        """选择快照源目录。"""

        selected = filedialog.askdirectory(parent=self, title=ui_text.SELECT_SOURCE_DIRECTORY_TITLE)
        if selected:
            self._snapshot_source_var.set(selected)

    def _choose_snapshot_output(self) -> None:
        """选择快照 HTML 输出位置。"""

        self._choose_output(self._snapshot_output_var, ui_text.SAVE_HTML_SNAPSHOT_TITLE)

    def _choose_compare_archive(self) -> None:
        """选择用于比对的基准 HTML 快照。"""

        selected = filedialog.askopenfilename(
            parent=self,
            title=ui_text.SELECT_BASELINE_SNAPSHOT_TITLE,
            filetypes=(("HTML", "*.html"), ("All files", "*.*")),
        )
        if selected:
            self._compare_archive_var.set(selected)

    def _choose_compare_source(self) -> None:
        """选择待检查的本机目录。"""

        selected = filedialog.askdirectory(parent=self, title=ui_text.SELECT_CHECK_DIRECTORY_TITLE)
        if selected:
            self._compare_source_var.set(selected)

    def _choose_compare_output(self) -> None:
        """选择比对报告输出位置。"""

        self._choose_output(self._compare_output_var, ui_text.SAVE_HTML_COMPARE_TITLE)

    def _choose_sqlite_database(self) -> None:
        """选择 SQLite 快照索引。"""

        selected = filedialog.askopenfilename(
            parent=self,
            title=ui_text.SELECT_SQLITE_SNAPSHOT_TITLE,
            filetypes=(("SQLite", "*.sqlite3 *.sqlite"), ("All files", "*.*")),
        )
        if selected:
            self._sqlite_database_var.set(selected)

    def _choose_sqlite_output(self) -> None:
        """选择从 SQLite 生成的 HTML 输出位置。"""

        self._choose_output(self._sqlite_output_var, ui_text.SAVE_HTML_FROM_SQLITE_TITLE)

    def _choose_output(self, variable: tk.StringVar, title: str) -> None:
        """打开 HTML 文件保存位置选择器。"""

        current = Path(variable.get()) if variable.get() else None
        selected = filedialog.asksaveasfilename(
            parent=self,
            title=title,
            defaultextension=".html",
            filetypes=(("HTML", "*.html"), ("All files", "*.*")),
            initialdir=str(current.parent) if current else None,
            initialfile=current.name if current else None,
        )
        if selected:
            variable.set(selected)

    def _suggest_snapshot_output(self, *_args: object) -> None:
        """根据源目录建议快照输出路径。"""

        value = self._snapshot_source_var.get()
        source = Path(value)
        if value and source.name and not self._snapshot_output_var.get():
            self._snapshot_output_var.set(
                str(source.parent / f"{source.name}_{date.today():%y-%m-%d}.html")
            )

    def _suggest_compare_output(self, *_args: object) -> None:
        """根据比对输入建议报告输出路径。"""

        if self._compare_output_var.get():
            return
        anchor = Path(self._compare_archive_var.get() or self._compare_source_var.get())
        if anchor.name:
            self._compare_output_var.set(str(anchor.parent / f"compare_{date.today():%Y%m%d}.html"))

    def _suggest_sqlite_output(self, *_args: object) -> None:
        """根据 SQLite 路径建议 HTML 输出路径。"""

        value = self._sqlite_database_var.get()
        database = Path(value)
        if value and database.name and not self._sqlite_output_var.get():
            self._sqlite_output_var.set(str(database.with_name(f"{database.stem}-new.html")))

    def _archive_changed(self, *_args: object) -> None:
        """重置快照内目录，并读取 HTML 指定的 Hash 策略。"""

        self._compare_archive_directory = ""
        self._compare_directory_var.set(f"{ui_text.SNAPSHOT_DIRECTORY}: {ui_text.SNAPSHOT_ROOT}")
        self._compare_hash_strategy_var.set(ui_text.HTML_HASH_PENDING)
        self._suggest_compare_output()
        value = self._compare_archive_var.get().strip()
        path = Path(value)
        if not value or not path.is_file():
            return
        try:
            config = html_snapshot_scan_config(path, self._scan_config)
        except (OSError, ValueError):
            return
        self._compare_hash_strategy_var.set(_hash_strategy_label(config))

    def _choose_archived_directory(self) -> None:
        """打开对话框选择需要比较的快照内目录。"""

        archive = self._validate_archive(self._compare_archive_var, self._compare_archive_error)
        if archive is None:
            return
        try:
            dialog = ArchiveDirectoryDialog(archive, self)
        except (OSError, ValueError) as exc:
            self._set_error(self._compare_archive_error, str(exc))
            return
        if dialog.show_modal():
            selected = dialog.selected_directory()
            if selected is not None:
                self._compare_archive_directory = selected
                label = selected or ui_text.SNAPSHOT_ROOT
                self._compare_directory_var.set(f"{ui_text.SNAPSHOT_DIRECTORY}: {label}")

    def _set_error(self, label: ttk.Label, message: str) -> None:
        """在对应输入字段下显示或清除校验错误。"""

        label.configure(text=message)
        if message:
            label.pack(anchor=tk.W, fill=tk.X, pady=(2, 0))
        else:
            label.pack_forget()

    def _validate_directory(self, variable: tk.StringVar, error: ttk.Label) -> Path | None:
        """校验输入目录是否存在。"""

        path = Path(variable.get().strip())
        if not path.is_dir():
            self._set_error(error, ui_text.DIRECTORY_REQUIRED)
            return None
        self._set_error(error, "")
        return path

    def _validate_archive(self, variable: tk.StringVar, error: ttk.Label) -> Path | None:
        """校验基准快照是否有效。"""

        path = Path(variable.get().strip())
        if not path.is_file() or path.suffix.lower() != ".html":
            self._set_error(error, ui_text.ARCHIVE_REQUIRED)
            return None
        try:
            html_snapshot_directories(path)
            html_snapshot_scan_config(path, self._scan_config)
        except (OSError, ValueError) as exc:
            self._set_error(error, f"{ui_text.ARCHIVE_INVALID}: {exc}")
            return None
        self._set_error(error, "")
        return path

    def _validate_sqlite(self, variable: tk.StringVar, error: ttk.Label) -> Path | None:
        """校验 SQLite 快照索引。"""

        path = Path(variable.get().strip())
        if not path.is_file() or path.suffix.lower() not in {".sqlite3", ".sqlite"}:
            self._set_error(error, ui_text.SQLITE_REQUIRED)
            return None
        self._set_error(error, "")
        return path

    def _validate_output(self, variable: tk.StringVar, error: ttk.Label) -> Path | None:
        """校验 HTML 输出路径是否可写且尚不存在。"""

        path = Path(variable.get().strip())
        if path.suffix.lower() != ".html":
            self._set_error(error, ui_text.OUTPUT_HTML_REQUIRED)
            return None
        if path.exists():
            self._set_error(error, ui_text.OUTPUT_EXISTS)
            return None
        if not path.parent.is_dir() or not os.access(path.parent, os.W_OK):
            self._set_error(error, ui_text.OUTPUT_NOT_WRITABLE)
            return None
        self._set_error(error, "")
        return path

    def _start_snapshot_from_page(self) -> None:
        """校验字段并启动快照生成任务。"""

        source = self._validate_directory(self._snapshot_source_var, self._snapshot_source_error)
        output = self._validate_output(self._snapshot_output_var, self._snapshot_output_error)
        if source is None or output is None or self._active_scan_running():
            return
        try:
            hash_mode = HashMode(self._snapshot_hash_mode_var.get())
            changes: dict[str, object] = {
                "follow_links": self._snapshot_follow_var.get(),
                "hash_mode": hash_mode,
            }
            if hash_mode is HashMode.SAMPLED:
                changes["sample_budget"] = (
                    int(self._snapshot_sample_budget_mb_var.get()) * _MEBIBYTE
                )
                changes["sample_count"] = int(self._snapshot_sample_count_var.get())
            config = replace(self._scan_config, **changes)
        except ValueError as exc:
            self._set_error(self._snapshot_hash_error, str(exc))
            return
        self._set_error(self._snapshot_hash_error, "")
        controller = ScanController()
        thread = HtmlSnapshotThread(source, output, config, controller)
        self._begin_task(
            thread,
            controller,
            ui_text.CREATE_SNAPSHOT_STAGE,
            True,
            self._snapshot_completed,
        )

    def _start_compare_from_page(self) -> None:
        """校验字段并启动目录比对任务。"""

        archive = self._validate_archive(self._compare_archive_var, self._compare_archive_error)
        source = self._validate_directory(self._compare_source_var, self._compare_source_error)
        output = self._validate_output(self._compare_output_var, self._compare_output_error)
        if archive is None or source is None or output is None or self._active_scan_running():
            return
        try:
            config = html_snapshot_scan_config(
                archive,
                replace(self._scan_config, follow_links=self._compare_follow_var.get()),
            )
        except (OSError, ValueError) as exc:
            self._set_error(self._compare_archive_error, f"{ui_text.ARCHIVE_INVALID}: {exc}")
            return
        controller = ScanController()
        thread = HtmlDirectoryCompareThread(
            archive,
            self._compare_archive_directory,
            source,
            output,
            config,
            controller,
        )
        self._begin_task(
            thread,
            controller,
            ui_text.CREATE_COMPARE_STAGE,
            True,
            self._compare_completed,
        )

    def _start_sqlite_from_page(self) -> None:
        """校验字段并启动 SQLite 渲染任务。"""

        database = self._validate_sqlite(self._sqlite_database_var, self._sqlite_database_error)
        output = self._validate_output(self._sqlite_output_var, self._sqlite_output_error)
        if database is None or output is None or self._active_scan_running():
            return
        thread = SqliteHtmlRenderThread(database, output)
        self._begin_task(
            thread,
            None,
            ui_text.CREATE_SQLITE_STAGE,
            False,
            self._snapshot_completed,
        )

    def _begin_task(
        self,
        thread: BackgroundTask,
        controller: ScanController | None,
        stage: str,
        controllable: bool,
        completion_handler: Callable[[str], None],
    ) -> None:
        """切换界面到任务运行状态。"""

        self._active_scan_thread = thread
        self._active_scan_controller = controller
        self._completion_handler = completion_handler
        self._last_output = None
        self._result_panel.pack_forget()
        self._run_stage_var.set(f"{ui_text.CURRENT_STAGE}: {stage}")
        self._run_path_var.set(f"{ui_text.CURRENT_PATH}: {ui_text.WAITING_SCAN}")
        self._run_files_var.set(f"{ui_text.FILES_SCANNED}: 0")
        self._run_hash_var.set(f"{ui_text.HASH_PROGRESS}: 0 B")
        self._run_progress.configure(mode="indeterminate", value=0)
        self._run_progress.start(12)
        for button in (
            self._pause_button,
            self._resume_button,
            self._cancel_button,
        ):
            if controllable:
                button.pack(side=tk.LEFT, padx=(0, 6))
            else:
                button.pack_forget()
        self._run_panel.pack(fill=tk.X, pady=(10, 0))
        self._language_selector.configure(state="disabled")
        self._show_status(stage)
        thread.start()
        self._task_poll_after = self.after(30, self._drain_task_events)

    def _drain_task_events(self) -> None:
        """在 Tk 主线程中消费后台任务事件。"""

        self._task_poll_after = None
        thread = self._active_scan_thread
        if thread is None:
            return
        while True:
            try:
                event, value = thread.events.get_nowait()
            except queue.Empty:
                break
            if event == "progress" and isinstance(value, ScanProgress):
                self._scan_progress(value)
            elif event == "completed" and self._completion_handler is not None:
                self._completion_handler(str(value))
            elif event == "failed":
                self._scan_failed(str(value))
        if thread.is_alive() or not thread.events.empty():
            self._task_poll_after = self.after(30, self._drain_task_events)

    def _active_scan_running(self) -> bool:
        """返回当前扫描任务是否仍在运行。"""

        return self._active_scan_thread is not None and self._active_scan_thread.is_alive()

    def _scan_progress(self, progress: ScanProgress) -> None:
        """更新扫描、Hash 和总体进度信息。"""

        total = max(progress.files_seen, 1)
        self._run_progress.stop()
        self._run_progress.configure(
            mode="determinate",
            maximum=1000,
            value=min(1000, int(progress.files_completed * 1000 / total)),
        )
        self._run_stage_var.set(f"{ui_text.CURRENT_STAGE}: {ui_text.SCANNING_HASH_STAGE}")
        self._run_path_var.set(
            f"{ui_text.CURRENT_PATH}: {progress.current_path or ui_text.WAITING_FILE}"
        )
        self._run_files_var.set(
            f"{ui_text.FILES_SCANNED}: {progress.files_completed}/{progress.files_seen}"
        )
        self._run_hash_var.set(
            f"{ui_text.HASH_PROGRESS}: "
            f"{progress.bytes_hashed / 1024 / 1024:.1f} MiB, "
            f"{progress.bytes_per_second / 1024 / 1024:.1f} MiB/s"
        )

    def _active_scan_control(self, action: str) -> None:
        """向当前扫描控制器发送操作。"""

        if self._active_scan_controller is None or not self._active_scan_running():
            return
        getattr(self._active_scan_controller, action)()
        labels = {
            "pause": ui_text.PAUSE,
            "resume": ui_text.RESUME,
            "cancel": ui_text.CANCEL,
        }
        self._run_stage_var.set(
            f"{ui_text.CURRENT_STAGE}: {ui_text.REQUESTED_ACTION}{labels[action]}"
        )

    def pause_active_scan(self) -> None:
        """暂停当前扫描任务。"""

        self._active_scan_control("pause")

    def resume_active_scan(self) -> None:
        """继续当前扫描任务。"""

        self._active_scan_control("resume")

    def cancel_active_scan(self) -> None:
        """取消当前扫描任务。"""

        self._active_scan_control("cancel")

    def _task_completed(self, output: str, message: str) -> None:
        """结束运行状态并显示输出结果。"""

        self._run_progress.stop()
        self._run_panel.pack_forget()
        self._last_output = Path(output)
        self._result_message_var.set(f"{ui_text.SUCCESS}: {output}")
        self._result_panel.pack(fill=tk.X, pady=(10, 0))
        self._language_selector.configure(state="readonly")
        self._show_status(message)

    def _snapshot_completed(self, output: str) -> None:
        """完成快照及 SQLite 索引生成。"""

        self._task_completed(output, ui_text.HTML_CREATED)

    def _compare_completed(self, output: str) -> None:
        """完成比对报告生成。"""

        self._task_completed(output, ui_text.COMPARE_CREATED)

    def _scan_failed(self, message: str) -> None:
        """结束运行状态并显示错误信息。"""

        self._run_progress.stop()
        self._run_panel.pack_forget()
        self._language_selector.configure(state="readonly")
        self._show_status(f"{ui_text.TASK_FAILED}: {message}", 10_000)

    def _show_status(self, message: str, timeout_ms: int | None = None) -> None:
        """显示状态文字，并可在超时后恢复就绪。"""

        if self._status_reset_after is not None:
            self.after_cancel(self._status_reset_after)
            self._status_reset_after = None
        self._status_var.set(message)
        if timeout_ms is not None:
            self._status_reset_after = self.after(
                timeout_ms, lambda: self._status_var.set(ui_text.READY)
            )

    def _open_output(self) -> None:
        """使用系统默认程序打开生成的 HTML。"""

        if self._last_output is not None:
            os.startfile(self._last_output)  # type: ignore[attr-defined]

    def _open_output_folder(self) -> None:
        """使用资源管理器打开输出文件所在目录。"""

        if self._last_output is not None:
            os.startfile(self._last_output.parent)  # type: ignore[attr-defined]

    def _close_window(self) -> None:
        """关闭窗口前请求取消仍在运行的扫描。"""

        if self._active_scan_controller is not None and self._active_scan_running():
            self._active_scan_controller.cancel()
        if self._task_poll_after is not None:
            self.after_cancel(self._task_poll_after)
            self._task_poll_after = None
        if self._status_reset_after is not None:
            self.after_cancel(self._status_reset_after)
            self._status_reset_after = None
        self._run_progress.stop()
        self.destroy()


def main() -> int:
    """启动 DiskHTML 桌面生成界面。"""

    window = MainWindow()
    window.mainloop()
    return 0

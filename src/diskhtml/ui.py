"""DiskHTML 的 HTML 快照桌面生成界面。"""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import ui_text
from .config import ScanConfig
from .html_archive import (
    compare_html_directory_to_source,
    create_html_snapshot,
    html_snapshot_directories,
    render_html_snapshot_from_sqlite,
)
from .models import ScanProgress
from .scanner import ScanController


class DropPathEdit(QLineEdit):
    """支持拖放文件或目录路径的输入框。"""

    path_dropped = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """在拖入内容包含本地 URL 时接受事件。"""

        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """读取首个本地 URL 并填入路径。"""

        urls = event.mimeData().urls()
        if not urls:
            event.ignore()
            return
        path = urls[0].toLocalFile()
        if not path:
            event.ignore()
            return
        self.setText(path)
        self.path_dropped.emit(path)
        event.acceptProposedAction()


class HtmlSnapshotThread(QThread):
    """在后台生成目录快照 HTML。"""

    completed = pyqtSignal(str)
    progress = pyqtSignal(object)
    failed = pyqtSignal(str)

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
                self.source, self.output, self.config, self.progress.emit, self.controller
            )
            self.completed.emit(str(output))
        except (OSError, RuntimeError, ValueError) as exc:
            self.failed.emit(str(exc))


class SqliteHtmlRenderThread(QThread):
    """从 SQLite 快照索引后台生成 HTML。"""

    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, database: Path, output: Path) -> None:
        super().__init__()
        self.database = database
        self.output = output

    def run(self) -> None:
        """执行离线 HTML 渲染。"""

        try:
            self.completed.emit(str(render_html_snapshot_from_sqlite(self.database, self.output)))
        except (OSError, RuntimeError, ValueError) as exc:
            self.failed.emit(str(exc))


class HtmlDirectoryCompareThread(QThread):
    """在后台比较 HTML 快照与本机目录。"""

    completed = pyqtSignal(str)
    progress = pyqtSignal(object)
    failed = pyqtSignal(str)

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
                self.progress.emit,
                self.controller,
            )
            self.completed.emit(str(output))
        except (OSError, RuntimeError, ValueError) as exc:
            self.failed.emit(str(exc))


class ArchiveDirectoryDialog(QDialog):
    """选择快照内目录的树形对话框。"""

    def __init__(self, archive: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(ui_text.SELECT_ARCHIVED_DIRECTORY)
        self.resize(560, 430)
        self._tree = QTreeWidget(self)
        self._tree.setHeaderLabel(f"{ui_text.BASELINE_SNAPSHOT} - {archive.name}")
        self._build_tree(html_snapshot_directories(archive))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self._tree)
        layout.addWidget(buttons)

    def selected_directory(self) -> str | None:
        """返回当前选择的快照内目录。"""

        item = self._tree.currentItem()
        if item is None:
            return None
        value = item.data(0, Qt.ItemDataRole.UserRole)
        return str(value) if value is not None else None

    def _build_tree(self, directories: tuple[str, ...]) -> None:
        """根据目录路径构建选择树。"""

        root = QTreeWidgetItem(self._tree, [ui_text.SNAPSHOT_ROOT])
        root.setData(0, Qt.ItemDataRole.UserRole, "")
        items = {"": root}
        for directory in directories:
            if not directory:
                continue
            parent_path = ""
            for part in directory.split("/"):
                current_path = f"{parent_path}/{part}".strip("/")
                if current_path not in items:
                    item = QTreeWidgetItem(items[parent_path], [part])
                    item.setData(0, Qt.ItemDataRole.UserRole, current_path)
                    items[current_path] = item
                parent_path = current_path
        self._tree.expandToDepth(1)
        self._tree.setCurrentItem(root)


class MainWindow(QMainWindow):
    """只负责配置并执行 HTML 生成任务的主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(ui_text.WINDOW_TITLE)
        self.resize(860, 590)
        self._scan_config = ScanConfig()
        self._compare_archive_directory = ""
        self._last_output: Path | None = None
        self._setup_central_content()
        self.statusBar().showMessage(ui_text.READY)

    def _setup_central_content(self) -> None:
        """构建任务页签及共享运行区域。"""

        content = QWidget(self)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 18, 28, 16)
        layout.setSpacing(10)
        self._tabs = QTabWidget(content)
        self._tabs.addTab(self._build_snapshot_page(), ui_text.TAB_SNAPSHOT)
        self._tabs.addTab(self._build_compare_page(), ui_text.TAB_COMPARE)
        self._tabs.addTab(self._build_sqlite_page(), ui_text.TAB_SQLITE)
        layout.addWidget(self._tabs)
        self._run_panel = self._build_run_panel(content)
        layout.addWidget(self._run_panel)
        self._result_panel = self._build_result_panel(content)
        layout.addWidget(self._result_panel)
        self.setCentralWidget(content)
        self.setStyleSheet(
            "QTabWidget::pane{border:1px solid #d7dce1;border-top:0;}"
            "QTabBar::tab{padding:10px 22px;font-size:14px;}"
            "QTabBar::tab:selected{border-bottom:3px solid #126ac5;color:#126ac5;}"
            "QLineEdit{min-height:32px;border:1px solid #aeb8c2;border-radius:4px;padding:4px 8px;}"
            "QPushButton{min-height:32px;padding:4px 14px;}"
            "QPushButton#primary{background:#126ac5;color:white;border:0;border-radius:4px;font-weight:600;padding:7px 20px;}"
            "QPushButton#primary:hover{background:#075aa9;}"
            "QLabel#description{color:#68737d;} QLabel#error{color:#bb2424;}"
            "QFrame#runPanel,QFrame#resultPanel{border:1px solid #cbd3d8;border-radius:4px;background:#f8fafb;}"
        )

    def _page_frame(self, heading: str, description: str) -> tuple[QWidget, QVBoxLayout]:
        """创建带标题与说明的任务页面。"""

        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        title = QLabel(heading, page)
        title.setStyleSheet("font-size:22px;font-weight:600;")
        description_label = QLabel(description, page)
        description_label.setObjectName("description")
        layout.addWidget(title)
        layout.addWidget(description_label)
        layout.addSpacing(8)
        return page, layout

    def _field(
        self,
        layout: QVBoxLayout,
        label: str,
        description: str,
        button_label: str,
        callback,
    ) -> tuple[DropPathEdit, QLabel]:
        """创建路径输入字段及其校验提示。"""

        title = QLabel(label)
        title.setStyleSheet("font-weight:600;")
        edit = DropPathEdit(self)
        button = QPushButton(button_label, self)
        button.setMinimumWidth(130)
        button.clicked.connect(callback)
        row = QHBoxLayout()
        row.addWidget(edit, 1)
        row.addWidget(button)
        detail = QLabel(description)
        detail.setObjectName("description")
        detail.setWordWrap(True)
        error = QLabel("")
        error.setObjectName("error")
        error.hide()
        layout.addWidget(title)
        layout.addLayout(row)
        layout.addWidget(detail)
        layout.addWidget(error)
        return edit, error

    def _build_snapshot_page(self) -> QWidget:
        """构建生成目录快照任务页。"""

        page, layout = self._page_frame(ui_text.SNAPSHOT_HEADING, ui_text.SNAPSHOT_DESCRIPTION)
        self._snapshot_source, self._snapshot_source_error = self._field(
            layout,
            ui_text.SOURCE_DIRECTORY,
            ui_text.SNAPSHOT_SOURCE_HELP,
            ui_text.SELECT_DIRECTORY,
            self._choose_snapshot_source,
        )
        self._snapshot_output, self._snapshot_output_error = self._field(
            layout,
            ui_text.OUTPUT_HTML,
            ui_text.SNAPSHOT_OUTPUT_HELP,
            ui_text.CHANGE_LOCATION,
            self._choose_snapshot_output,
        )
        self._snapshot_source.textChanged.connect(self._suggest_snapshot_output)
        self._snapshot_source.path_dropped.connect(self._suggest_snapshot_output)
        self._snapshot_follow = QCheckBox(ui_text.FOLLOW_LINKS, page)
        self._snapshot_follow.setChecked(self._scan_config.follow_links)
        layout.addWidget(self._snapshot_follow)
        layout.addStretch()
        button_row = QHBoxLayout()
        button_row.addStretch()
        action = QPushButton(ui_text.CREATE_SNAPSHOT, page)
        action.setObjectName("primary")
        action.clicked.connect(self._start_snapshot_from_page)
        button_row.addWidget(action)
        layout.addLayout(button_row)
        return page

    def _build_compare_page(self) -> QWidget:
        """构建生成比对报告任务页。"""

        page, layout = self._page_frame(ui_text.COMPARE_HEADING, ui_text.COMPARE_DESCRIPTION)
        self._compare_archive, self._compare_archive_error = self._field(
            layout,
            ui_text.BASELINE_SNAPSHOT,
            ui_text.ARCHIVE_HELP,
            ui_text.SELECT_SNAPSHOT,
            self._choose_compare_archive,
        )
        self._compare_source, self._compare_source_error = self._field(
            layout,
            ui_text.CHECK_DIRECTORY,
            ui_text.CHECK_DIRECTORY_HELP,
            ui_text.SELECT_DIRECTORY,
            self._choose_compare_source,
        )
        directory_row = QHBoxLayout()
        self._compare_directory_label = QLabel(
            f"{ui_text.SNAPSHOT_DIRECTORY}: {ui_text.SNAPSHOT_ROOT}", page
        )
        choose_directory = QPushButton(ui_text.SELECT_ARCHIVED_DIRECTORY, page)
        choose_directory.clicked.connect(self._choose_archived_directory)
        directory_row.addWidget(self._compare_directory_label, 1)
        directory_row.addWidget(choose_directory)
        layout.addLayout(directory_row)
        self._compare_output, self._compare_output_error = self._field(
            layout,
            ui_text.OUTPUT_REPORT,
            ui_text.COMPARE_OUTPUT_HELP,
            ui_text.CHANGE_LOCATION,
            self._choose_compare_output,
        )
        self._compare_archive.textChanged.connect(self._archive_changed)
        self._compare_archive.path_dropped.connect(self._archive_changed)
        self._compare_source.textChanged.connect(self._suggest_compare_output)
        self._compare_source.path_dropped.connect(self._suggest_compare_output)
        self._compare_follow = QCheckBox(ui_text.FOLLOW_LINKS, page)
        self._compare_follow.setChecked(self._scan_config.follow_links)
        layout.addWidget(self._compare_follow)
        layout.addStretch()
        button_row = QHBoxLayout()
        button_row.addStretch()
        action = QPushButton(ui_text.CREATE_COMPARE, page)
        action.setObjectName("primary")
        action.clicked.connect(self._start_compare_from_page)
        button_row.addWidget(action)
        layout.addLayout(button_row)
        return page

    def _build_sqlite_page(self) -> QWidget:
        """构建从 SQLite 生成 HTML 的任务页。"""

        page, layout = self._page_frame(ui_text.SQLITE_HEADING, ui_text.SQLITE_DESCRIPTION)
        self._sqlite_database, self._sqlite_database_error = self._field(
            layout,
            ui_text.SQLITE_INDEX,
            ui_text.SQLITE_HELP,
            ui_text.SELECT_SQLITE,
            self._choose_sqlite_database,
        )
        self._sqlite_output, self._sqlite_output_error = self._field(
            layout,
            ui_text.OUTPUT_HTML,
            ui_text.SQLITE_OUTPUT_HELP,
            ui_text.CHANGE_LOCATION,
            self._choose_sqlite_output,
        )
        self._sqlite_database.textChanged.connect(self._suggest_sqlite_output)
        self._sqlite_database.path_dropped.connect(self._suggest_sqlite_output)
        layout.addStretch()
        button_row = QHBoxLayout()
        button_row.addStretch()
        action = QPushButton(ui_text.CREATE_SQLITE, page)
        action.setObjectName("primary")
        action.clicked.connect(self._start_sqlite_from_page)
        button_row.addWidget(action)
        layout.addLayout(button_row)
        return page

    def _build_run_panel(self, parent: QWidget) -> QFrame:
        """构建任务运行状态区域。"""

        panel = QFrame(parent)
        panel.setObjectName("runPanel")
        layout = QVBoxLayout(panel)
        self._run_stage = QLabel("")
        self._run_path = QLabel("")
        self._run_files = QLabel("")
        self._run_hash = QLabel("")
        self._run_progress = QProgressBar(panel)
        self._run_progress.setRange(0, 0)
        controls = QHBoxLayout()
        self._pause_button = QPushButton(ui_text.PAUSE, panel)
        self._resume_button = QPushButton(ui_text.RESUME, panel)
        self._cancel_button = QPushButton(ui_text.CANCEL, panel)
        self._pause_button.clicked.connect(self.pause_active_scan)
        self._resume_button.clicked.connect(self.resume_active_scan)
        self._cancel_button.clicked.connect(self.cancel_active_scan)
        controls.addWidget(self._pause_button)
        controls.addWidget(self._resume_button)
        controls.addWidget(self._cancel_button)
        controls.addStretch()
        for widget in (
            self._run_stage,
            self._run_path,
            self._run_files,
            self._run_hash,
            self._run_progress,
        ):
            layout.addWidget(widget)
        layout.addLayout(controls)
        panel.hide()
        return panel

    def _build_result_panel(self, parent: QWidget) -> QFrame:
        """构建任务完成后的输出操作区域。"""

        panel = QFrame(parent)
        panel.setObjectName("resultPanel")
        layout = QHBoxLayout(panel)
        self._result_message = QLabel("")
        self._result_message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        open_html = QPushButton(ui_text.OPEN_HTML, panel)
        open_folder = QPushButton(ui_text.OPEN_FOLDER, panel)
        open_html.clicked.connect(self._open_output)
        open_folder.clicked.connect(self._open_output_folder)
        layout.addWidget(self._result_message, 1)
        layout.addWidget(open_html)
        layout.addWidget(open_folder)
        panel.hide()
        return panel

    def _choose_snapshot_source(self) -> None:
        """选择快照源目录。"""

        selected = QFileDialog.getExistingDirectory(self, ui_text.DIRECTORY_REQUIRED)
        if selected:
            self._snapshot_source.setText(selected)

    def _choose_snapshot_output(self) -> None:
        """选择快照 HTML 输出位置。"""

        self._choose_output(self._snapshot_output, "Save HTML snapshot")

    def _choose_compare_archive(self) -> None:
        """Helper."""

        selected, _ = QFileDialog.getOpenFileName(
            self, "Select baseline snapshot", filter="HTML files (*.html)"
        )
        if selected:
            self._compare_archive.setText(selected)

    def _choose_compare_source(self) -> None:
        """选择待检查的本机目录。"""

        selected = QFileDialog.getExistingDirectory(self, "Select directory to check")
        if selected:
            self._compare_source.setText(selected)

    def _choose_compare_output(self) -> None:
        """选择比对报告输出位置。"""

        self._choose_output(self._compare_output, "Save HTML comparison")

    def _choose_sqlite_database(self) -> None:
        """选择 SQLite 快照索引。"""

        selected, _ = QFileDialog.getOpenFileName(
            self, "Select SQLite snapshot", filter="SQLite files (*.sqlite3 *.sqlite)"
        )
        if selected:
            self._sqlite_database.setText(selected)

    def _choose_sqlite_output(self) -> None:
        """选择从 SQLite 生成的 HTML 输出位置。"""

        self._choose_output(self._sqlite_output, "Render HTML from SQLite")

    def _choose_output(self, edit: DropPathEdit, title: str) -> None:
        """打开 HTML 文件保存位置选择器。"""

        selected, _ = QFileDialog.getSaveFileName(self, title, edit.text(), "HTML files (*.html)")
        if selected:
            edit.setText(selected)

    def _suggest_snapshot_output(self, value: str) -> None:
        """根据源目录建议快照输出路径。"""

        source = Path(value)
        if value and source.name and not self._snapshot_output.text():
            self._snapshot_output.setText(
                str(source.parent / f"{source.name}-{date.today():%y-%m-%d}.html")
            )

    def _suggest_compare_output(self, _value: str = "") -> None:
        """根据比对输入建议报告输出路径。"""

        if self._compare_output.text():
            return
        anchor = Path(self._compare_archive.text() or self._compare_source.text())
        if anchor.name:
            self._compare_output.setText(str(anchor.parent / f"compare_{date.today():%Y%m%d}.html"))

    def _suggest_sqlite_output(self, value: str) -> None:
        """根据 SQLite 路径建议 HTML 输出路径。"""

        database = Path(value)
        if value and database.name and not self._sqlite_output.text():
            self._sqlite_output.setText(str(database.with_name(f"{database.stem}-new.html")))

    def _archive_changed(self, _value: str = "") -> None:
        """重置快照内目录并更新输出建议。"""

        self._compare_archive_directory = ""
        self._compare_directory_label.setText(
            f"{ui_text.SNAPSHOT_DIRECTORY}: {ui_text.SNAPSHOT_ROOT}"
        )
        self._suggest_compare_output()

    def _choose_archived_directory(self) -> None:
        """打开对话框选择需要比较的快照内目录。"""

        archive = self._validate_archive(self._compare_archive, self._compare_archive_error)
        if archive is None:
            return
        try:
            dialog = ArchiveDirectoryDialog(archive, self)
        except (OSError, ValueError) as exc:
            self._set_error(self._compare_archive_error, str(exc))
            return
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = dialog.selected_directory()
            if selected is not None:
                self._compare_archive_directory = selected
                label = selected or ui_text.SNAPSHOT_ROOT
                self._compare_directory_label.setText(f"{ui_text.SNAPSHOT_DIRECTORY}: {label}")
        dialog.deleteLater()

    def _set_error(self, label: QLabel, message: str) -> None:
        """Helper."""

        label.setText(message)
        label.setVisible(bool(message))

    def _validate_directory(self, edit: DropPathEdit, error: QLabel) -> Path | None:
        """校验输入目录是否存在。"""

        path = Path(edit.text().strip())
        if not path.is_dir():
            self._set_error(error, ui_text.DIRECTORY_REQUIRED)
            return None
        self._set_error(error, "")
        return path

    def _validate_archive(self, edit: DropPathEdit, error: QLabel) -> Path | None:
        """校验基准快照是否有效。"""

        path = Path(edit.text().strip())
        if not path.is_file() or path.suffix.lower() != ".html":
            self._set_error(error, ui_text.ARCHIVE_REQUIRED)
            return None
        try:
            html_snapshot_directories(path)
        except (OSError, ValueError) as exc:
            self._set_error(error, f"{ui_text.ARCHIVE_INVALID}: {exc}")
            return None
        self._set_error(error, "")
        return path

    def _validate_sqlite(self, edit: DropPathEdit, error: QLabel) -> Path | None:
        """校验 SQLite 快照索引。"""

        path = Path(edit.text().strip())
        if not path.is_file() or path.suffix.lower() not in {".sqlite3", ".sqlite"}:
            self._set_error(error, ui_text.SQLITE_REQUIRED)
            return None
        self._set_error(error, "")
        return path

    def _validate_output(self, edit: DropPathEdit, error: QLabel) -> Path | None:
        """校验 HTML 输出路径是否可写且尚不存在。"""

        path = Path(edit.text().strip())
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

        source = self._validate_directory(self._snapshot_source, self._snapshot_source_error)
        output = self._validate_output(self._snapshot_output, self._snapshot_output_error)
        if source is None or output is None or self._active_scan_running():
            return
        config = replace(self._scan_config, follow_links=self._snapshot_follow.isChecked())
        controller = ScanController()
        thread = HtmlSnapshotThread(source, output, config, controller)
        thread.progress.connect(self._scan_progress)
        thread.completed.connect(self._snapshot_completed)
        thread.failed.connect(self._scan_failed)
        self._begin_task(thread, controller, ui_text.CREATE_SNAPSHOT_STAGE, True)

    def _start_compare_from_page(self) -> None:
        """校验字段并启动目录比对任务。"""

        archive = self._validate_archive(self._compare_archive, self._compare_archive_error)
        source = self._validate_directory(self._compare_source, self._compare_source_error)
        output = self._validate_output(self._compare_output, self._compare_output_error)
        if archive is None or source is None or output is None or self._active_scan_running():
            return
        config = replace(self._scan_config, follow_links=self._compare_follow.isChecked())
        controller = ScanController()
        thread = HtmlDirectoryCompareThread(
            archive, self._compare_archive_directory, source, output, config, controller
        )
        thread.progress.connect(self._scan_progress)
        thread.completed.connect(self._compare_completed)
        thread.failed.connect(self._scan_failed)
        self._begin_task(thread, controller, ui_text.CREATE_COMPARE_STAGE, True)

    def _start_sqlite_from_page(self) -> None:
        """校验字段并启动 SQLite 渲染任务。"""

        database = self._validate_sqlite(self._sqlite_database, self._sqlite_database_error)
        output = self._validate_output(self._sqlite_output, self._sqlite_output_error)
        if database is None or output is None or self._active_scan_running():
            return
        thread = SqliteHtmlRenderThread(database, output)
        thread.completed.connect(self._snapshot_completed)
        thread.failed.connect(self._scan_failed)
        self._begin_task(thread, None, ui_text.CREATE_SQLITE_STAGE, False)

    def _begin_task(
        self, thread: QThread, controller: ScanController | None, stage: str, controllable: bool
    ) -> None:
        """切换界面到任务运行状态。"""

        self._active_scan_thread = thread
        self._active_scan_controller = controller
        self._last_output = None
        self._result_panel.hide()
        self._run_stage.setText(f"{ui_text.CURRENT_STAGE}: {stage}")
        self._run_path.setText(f"{ui_text.CURRENT_PATH}: {ui_text.WAITING_SCAN}")
        self._run_files.setText(f"{ui_text.FILES_SCANNED}: 0")
        self._run_hash.setText(f"{ui_text.HASH_PROGRESS}: 0 B")
        self._run_progress.setRange(0, 0)
        for button in (self._pause_button, self._resume_button, self._cancel_button):
            button.setVisible(controllable)
        self._run_panel.show()
        self.statusBar().showMessage(stage)
        thread.start()

    def _active_scan_running(self) -> bool:
        """返回当前扫描任务是否仍在运行。"""

        thread = getattr(self, "_active_scan_thread", None)
        return thread is not None and thread.isRunning()

    def _scan_progress(self, progress: ScanProgress) -> None:
        """更新扫描、Hash 和总体进度信息。"""

        total = max(progress.files_seen, 1)
        self._run_progress.setRange(0, 1000)
        self._run_progress.setValue(min(1000, int(progress.files_completed * 1000 / total)))
        self._run_stage.setText(f"{ui_text.CURRENT_STAGE}: {ui_text.SCANNING_HASH_STAGE}")
        self._run_path.setText(
            f"{ui_text.CURRENT_PATH}: {progress.current_path or ui_text.WAITING_FILE}"
        )
        self._run_files.setText(
            f"{ui_text.FILES_SCANNED}: {progress.files_completed}/{progress.files_seen}"
        )
        self._run_hash.setText(
            f"{ui_text.HASH_PROGRESS}: {progress.bytes_hashed / 1024 / 1024:.1f} MiB, "
            f"{progress.bytes_per_second / 1024 / 1024:.1f} MiB/s"
        )

    def _active_scan_control(self, action: str) -> None:
        """向当前扫描控制器发送操作。"""

        controller = getattr(self, "_active_scan_controller", None)
        if controller is None or not self._active_scan_running():
            return
        getattr(controller, action)()
        labels = {"pause": ui_text.PAUSE, "resume": ui_text.RESUME, "cancel": ui_text.CANCEL}
        self._run_stage.setText(
            f"{ui_text.CURRENT_STAGE}: {ui_text.REQUESTED_ACTION}{labels[action]}"
        )

    def pause_active_scan(self) -> None:
        """暂停当前扫描任务。"""

        self._active_scan_control("pause")

    def resume_active_scan(self) -> None:
        """继续当前扫描任务。"""

        self._active_scan_control("resume")

    def cancel_active_scan(self) -> None:
        """Select snapshot source"""

        self._active_scan_control("cancel")

    def _task_completed(self, output: str, message: str) -> None:
        """结束运行状态并显示输出结果。"""

        self._run_panel.hide()
        self._last_output = Path(output)
        self._result_message.setText(f"{ui_text.SUCCESS}: {output}")
        self._result_panel.show()
        self.statusBar().showMessage(message)

    def _snapshot_completed(self, output: str) -> None:
        """完成快照及 SQLite 索引生成。"""

        self._task_completed(output, ui_text.HTML_CREATED)

    def _compare_completed(self, output: str) -> None:
        """完成比对报告生成。"""

        self._task_completed(output, ui_text.COMPARE_CREATED)

    def _scan_failed(self, message: str) -> None:
        """结束运行状态并显示错误信息。"""

        self._run_panel.hide()
        self.statusBar().showMessage(f"{ui_text.TASK_FAILED}: {message}", 10_000)

    def _open_output(self) -> None:
        """使用系统默认程序打开生成的 HTML。"""

        if self._last_output is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_output)))

    def _open_output_folder(self) -> None:
        """使用资源管理器打开输出文件所在目录。"""

        if self._last_output is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_output.parent)))


def main() -> int:
    """启动 DiskHTML 桌面生成界面。"""

    application = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return application.exec()

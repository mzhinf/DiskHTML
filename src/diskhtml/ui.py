"""DiskHTML 单文件 HTML 快照图形界面。"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .config import ScanConfig
from .html_archive import (
    compare_html_directory_to_source,
    create_html_snapshot,
    html_snapshot_directories,
    render_html_snapshot_from_sqlite,
)
from .models import ScanProgress
from .scanner import ScanController


class HtmlSnapshotThread(QThread):
    """在后台扫描路径并生成单文件 HTML 快照，避免阻塞主界面。"""

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
        """调用 HTML 快照服务并将进度、结果或错误发回主线程。"""

        try:
            output = create_html_snapshot(
                self.source,
                self.output,
                self.config,
                self.progress.emit,
                self.controller,
            )
            self.completed.emit(str(output))
        except (OSError, RuntimeError, ValueError) as exc:
            self.failed.emit(str(exc))


class SqliteHtmlRenderThread(QThread):
    """在后台从 SQLite 快照索引生成当前版本 HTML。"""

    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, database: Path, output: Path) -> None:
        super().__init__()
        self.database = database
        self.output = output

    def run(self) -> None:
        """读取已完成扫描并输出当前版本的单文件 HTML。"""

        try:
            self.completed.emit(str(render_html_snapshot_from_sqlite(self.database, self.output)))
        except (OSError, RuntimeError, ValueError) as exc:
            self.failed.emit(str(exc))


class HtmlDirectoryCompareThread(QThread):
    """在后台将 HTML 快照中的已选目录与本机目录比较。"""

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
        """扫描本机目录并生成单文件 HTML 比较报告。"""

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
    """展示 HTML 快照目录树并让用户选择一个历史目录。"""

    def __init__(self, archive: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("从 HTML 快照选择目录")
        self.resize(620, 480)
        self._tree = QTreeWidget(self)
        self._tree.setHeaderLabel(f"快照目录：{archive.name}")
        self._build_tree(html_snapshot_directories(archive))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self._tree)
        layout.addWidget(buttons)

    def selected_directory(self) -> str | None:
        """返回选中目录；根目录使用空字符串。"""

        item = self._tree.currentItem()
        if item is None:
            return None
        value = item.data(0, Qt.ItemDataRole.UserRole)
        return str(value) if value is not None else None

    def _build_tree(self, directories: tuple[str, ...]) -> None:
        """将相对目录清单渲染为可选择的树，保留每项的完整相对路径。"""

        root = QTreeWidgetItem(self._tree, ["快照根目录"])
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
    """提供 HTML 快照、目录选择和本机目录比较工作流。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DiskHTML - HTML 快照")
        self.resize(760, 360)
        self._scan_config = ScanConfig()
        self._setup_central_content()
        self._setup_toolbar()
        self._scan_progress_bar = QProgressBar(self)
        self._scan_progress_bar.setRange(0, 0)
        self._scan_progress_bar.setTextVisible(False)
        self._scan_progress_bar.hide()
        self.statusBar().addPermanentWidget(self._scan_progress_bar)
        self.statusBar().showMessage("选择“生成快照 HTML”开始。")

    def _setup_central_content(self) -> None:
        """创建说明性主界面，避免暴露 SQLite 项目管理功能。"""

        content = QWidget(self)
        layout = QVBoxLayout(content)
        title = QLabel("将目录保存为可离线打开的 HTML 快照", content)
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        description = QLabel(
            "1. 生成快照 HTML：选择目录和保存位置，完成后得到一个可搜索的离线快照。"
            "\n2. 比较快照目录：从 HTML 快照树选择历史目录，再选择本机目录。"
            "\n扫描期间使用临时索引保障可靠性；交付物始终是单个 HTML 文件。",
            content,
        )
        description.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(description)
        self._follow_links = QCheckBox(
            "\u8ddf\u968f\u8f6f\u94fe\u63a5\u548c Windows \u91cd\u89e3\u6790\u76ee\u5f55", content
        )
        self._follow_links.setChecked(self._scan_config.follow_links)
        self._follow_links.toggled.connect(self._set_follow_links)
        layout.addWidget(self._follow_links)
        layout.addStretch()
        self.setCentralWidget(content)

    def _setup_toolbar(self) -> None:
        """仅保留 HTML 工作流真正需要的操作入口。"""

        toolbar = QToolBar("HTML 快照", self)
        self.addToolBar(toolbar)
        for label, callback in (
            ("\u751f\u6210\u5feb\u7167 HTML", self.create_snapshot),
            ("\u6bd4\u8f83\u5feb\u7167\u76ee\u5f55", self.compare_archive_directory),
            ("\u4ece SQLite \u751f\u6210\u5feb\u7167 HTML", self.render_sqlite_snapshot),
        ):
            button = QPushButton(label, self)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        toolbar.addSeparator()
        for label, callback in (
            ("暂停", self.pause_active_scan),
            ("继续", self.resume_active_scan),
            ("取消", self.cancel_active_scan),
        ):
            button = QPushButton(label, self)
            button.clicked.connect(callback)
            toolbar.addWidget(button)

    def create_snapshot(self) -> None:
        """选择目录和 HTML 输出位置后启动后台快照。"""

        source = QFileDialog.getExistingDirectory(self, "选择需要快照的目录")
        if not source:
            return
        source_path = Path(source)
        output, _ = QFileDialog.getSaveFileName(
            self,
            "保存 HTML 快照",
            str(source_path.parent / f"{source_path.name}-快照.html"),
            "HTML 文件 (*.html)",
        )
        if output:
            self._start_snapshot(source_path, Path(output))

    def _set_follow_links(self, enabled: bool) -> None:
        """\u540c\u6b65\u754c\u9762\u8f6f\u94fe\u63a5\u5f00\u5173\u5230\u540e\u7eed\u626b\u63cf\u548c\u6bd4\u8f83\u4efb\u52a1\u3002"""

        self._scan_config = replace(self._scan_config, follow_links=enabled)

    def _start_snapshot(self, source: Path, output: Path) -> None:
        """创建带可暂停控制器的后台 HTML 快照线程。"""

        if self._active_scan_running():
            self.statusBar().showMessage("已有扫描任务正在运行。", 5_000)
            return
        controller = ScanController()
        thread = HtmlSnapshotThread(source, output, self._scan_config, controller)
        thread.progress.connect(self._scan_progress)
        thread.completed.connect(self._snapshot_completed)
        thread.failed.connect(self._scan_failed)
        self._set_active_scan(thread, controller)
        self._scan_progress_bar.show()
        self.statusBar().showMessage("正在后台生成 HTML 快照。")
        thread.start()

    def render_sqlite_snapshot(self) -> None:
        """选择历史 SQLite 快照索引并生成当前版本 HTML 页面。"""

        database, _ = QFileDialog.getOpenFileName(
            self, "选择 SQLite 快照索引", filter="SQLite 文件 (*.sqlite3 *.sqlite);;所有文件 (*)"
        )
        if not database:
            return
        output, _ = QFileDialog.getSaveFileName(
            self, "从 SQLite 生成 HTML 快照", filter="HTML 文件 (*.html)"
        )
        if not output or self._active_scan_running():
            return
        thread = SqliteHtmlRenderThread(Path(database), Path(output))
        thread.completed.connect(self._snapshot_completed)
        thread.failed.connect(self._scan_failed)
        self._active_scan_thread = thread
        self.statusBar().showMessage("正在从 SQLite 快照索引生成 HTML。")
        thread.start()

    def compare_archive_directory(self) -> None:
        """从 HTML 快照树选择目录，并与用户选择的本机目录比较。"""

        filename, _ = QFileDialog.getOpenFileName(
            self, "选择历史 HTML 快照", filter="HTML 文件 (*.html)"
        )
        if not filename:
            return
        archive = Path(filename)
        try:
            dialog = ArchiveDirectoryDialog(archive, self)
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage(f"无法读取 HTML 快照：{exc}", 10_000)
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        archived_directory = dialog.selected_directory()
        if archived_directory is None:
            return
        source = QFileDialog.getExistingDirectory(self, "选择需要比较的本机目录")
        if not source:
            return
        output, _ = QFileDialog.getSaveFileName(
            self, "保存 HTML 比较报告", filter="HTML 文件 (*.html)"
        )
        if output:
            self._start_compare(archive, archived_directory, Path(source), Path(output))

    def _start_compare(
        self, archive: Path, archived_directory: str, source: Path, output: Path
    ) -> None:
        """创建后台“快照目录对本机目录”比较线程。"""

        if self._active_scan_running():
            self.statusBar().showMessage("已有扫描任务正在运行。", 5_000)
            return
        controller = ScanController()
        thread = HtmlDirectoryCompareThread(
            archive, archived_directory, source, output, self._scan_config, controller
        )
        thread.progress.connect(self._scan_progress)
        thread.completed.connect(self._compare_completed)
        thread.failed.connect(self._scan_failed)
        self._set_active_scan(thread, controller)
        self._scan_progress_bar.show()
        self.statusBar().showMessage("正在扫描本机目录并生成 HTML 比较报告。")
        thread.start()

    def _set_active_scan(self, thread: QThread, controller: ScanController) -> None:
        """保存当前可暂停、继续或取消的后台扫描任务。"""

        self._active_scan_thread = thread
        self._active_scan_controller = controller

    def _active_scan_running(self) -> bool:
        """判断当前是否有可控制的扫描任务。"""

        thread = getattr(self, "_active_scan_thread", None)
        return thread is not None and thread.isRunning()

    def _active_scan_control(self, action: str) -> None:
        """向当前扫描发送暂停、继续或取消请求。"""

        controller = getattr(self, "_active_scan_controller", None)
        if controller is None or not self._active_scan_running():
            self.statusBar().showMessage("当前没有可控制的扫描。", 5_000)
            return
        getattr(controller, action)()
        labels = {"pause": "暂停", "resume": "继续", "cancel": "取消"}
        self.statusBar().showMessage(f"已请求{labels[action]}扫描。", 5_000)

    def pause_active_scan(self) -> None:
        """请求在下一个文件边界暂停当前扫描。"""

        self._active_scan_control("pause")

    def resume_active_scan(self) -> None:
        """请求继续已暂停的扫描。"""

        self._active_scan_control("resume")

    def cancel_active_scan(self) -> None:
        """请求取消当前扫描。"""

        self._active_scan_control("cancel")

    def _scan_progress(self, progress: ScanProgress) -> None:
        """在状态栏显示快照或比较扫描的实时进度。"""

        self._scan_progress_bar.show()
        eta_text = (
            "未知"
            if progress.estimated_remaining_seconds is None
            else f"{progress.estimated_remaining_seconds:.0f} s"
        )
        self.statusBar().showMessage(
            f"扫描中：{progress.files_completed}/{progress.files_seen} 个文件，"
            f"{progress.bytes_hashed / 1024 / 1024:.1f} MiB，"
            f"{progress.bytes_per_second / 1024 / 1024:.1f} MiB/s，"
            f"ETA {eta_text}，{progress.current_path or ''}"
        )

    def _snapshot_completed(self, output: str) -> None:
        """显示 HTML 快照生成完成信息。"""

        self._scan_progress_bar.hide()
        self.statusBar().showMessage(f"HTML 快照已生成：{output}", 10_000)

    def _compare_completed(self, output: str) -> None:
        """显示 HTML 比较报告生成完成信息。"""

        self._scan_progress_bar.hide()
        self.statusBar().showMessage(f"HTML 比较报告已生成：{output}", 10_000)

    def _scan_failed(self, message: str) -> None:
        """显示快照或比较扫描失败原因。"""

        self._scan_progress_bar.hide()
        self.statusBar().showMessage(f"扫描失败：{message}", 10_000)


def main() -> int:
    """启动 HTML 快照图形界面。"""

    application = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return application.exec()

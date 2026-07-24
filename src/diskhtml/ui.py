"""DiskHTML 单文件 HTML 冷备图形界面。"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
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

from .config import ScanConfig, load_config
from .html_archive import (
    compare_html_directory_to_source,
    create_html_backup,
    html_backup_directories,
)
from .models import ScanProgress
from .scanner import ScanController


class HtmlBackupThread(QThread):
    """在后台扫描路径并生成单文件 HTML 冷备，避免阻塞主界面。"""

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
        """调用 HTML 冷备服务并将进度、结果或错误发回主线程。"""

        try:
            output = create_html_backup(
                self.source,
                self.output,
                self.config,
                self.progress.emit,
                self.controller,
            )
            self.completed.emit(str(output))
        except (OSError, RuntimeError, ValueError) as exc:
            self.failed.emit(str(exc))


class HtmlDirectoryCompareThread(QThread):
    """在后台将 HTML 冷备中的已选目录与本机目录比较。"""

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
    """展示 HTML 冷备目录树并让用户选择一个历史目录。"""

    def __init__(self, archive: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("从 HTML 冷备选择目录")
        self.resize(620, 480)
        self._tree = QTreeWidget(self)
        self._tree.setHeaderLabel(f"冷备目录：{archive.name}")
        self._build_tree(html_backup_directories(archive))
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

        root = QTreeWidgetItem(self._tree, ["冷备根目录"])
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
    """提供 HTML 冷备、目录选择和本机目录比较工作流。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DiskHTML - HTML 冷备")
        self.resize(760, 360)
        self._scan_config = ScanConfig()
        self._setup_central_content()
        self._setup_toolbar()
        self._scan_progress_bar = QProgressBar(self)
        self._scan_progress_bar.setRange(0, 0)
        self._scan_progress_bar.setTextVisible(False)
        self._scan_progress_bar.hide()
        self.statusBar().addPermanentWidget(self._scan_progress_bar)
        self.statusBar().showMessage("选择“生成冷备 HTML”开始。")

    def _setup_central_content(self) -> None:
        """创建说明性主界面，避免暴露 SQLite 项目管理功能。"""

        content = QWidget(self)
        layout = QVBoxLayout(content)
        title = QLabel("将目录保存为可离线打开的 HTML 冷备", content)
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        description = QLabel(
            "1. 生成冷备 HTML：选择目录和保存位置，完成后得到一个可搜索的离线快照。"
            "\n2. 比较冷备目录：从 HTML 冷备树选择历史目录，再选择本机目录。"
            "\n扫描期间使用临时索引保障可靠性；交付物始终是单个 HTML 文件。",
            content,
        )
        description.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addStretch()
        self.setCentralWidget(content)

    def _setup_toolbar(self) -> None:
        """仅保留 HTML 工作流真正需要的操作入口。"""

        toolbar = QToolBar("HTML 冷备", self)
        self.addToolBar(toolbar)
        for label, callback in (
            ("生成冷备 HTML", self.create_backup),
            ("比较冷备目录", self.compare_archive_directory),
            ("打开报告", self.open_report),
            ("扫描配置", self.load_scan_config),
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

    def create_backup(self) -> None:
        """选择目录和 HTML 输出位置后启动后台冷备。"""

        source = QFileDialog.getExistingDirectory(self, "选择需要冷备的目录")
        if not source:
            return
        source_path = Path(source)
        output, _ = QFileDialog.getSaveFileName(
            self,
            "保存 HTML 冷备",
            str(source_path.parent / f"{source_path.name}-冷备.html"),
            "HTML 文件 (*.html)",
        )
        if output:
            self._start_backup(source_path, Path(output))

    def _start_backup(self, source: Path, output: Path) -> None:
        """创建带可暂停控制器的后台 HTML 冷备线程。"""

        if self._active_scan_running():
            self.statusBar().showMessage("已有扫描任务正在运行。", 5_000)
            return
        controller = ScanController()
        thread = HtmlBackupThread(source, output, self._scan_config, controller)
        thread.progress.connect(self._scan_progress)
        thread.completed.connect(self._backup_completed)
        thread.failed.connect(self._scan_failed)
        self._set_active_scan(thread, controller)
        self._scan_progress_bar.show()
        self.statusBar().showMessage("正在后台生成 HTML 冷备。")
        thread.start()

    def compare_archive_directory(self) -> None:
        """从 HTML 冷备树选择目录，并与用户选择的本机目录比较。"""

        filename, _ = QFileDialog.getOpenFileName(
            self, "选择历史 HTML 冷备", filter="HTML 文件 (*.html)"
        )
        if not filename:
            return
        archive = Path(filename)
        try:
            dialog = ArchiveDirectoryDialog(archive, self)
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage(f"无法读取 HTML 冷备：{exc}", 10_000)
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
        """创建后台“冷备目录对本机目录”比较线程。"""

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

    def open_report(self) -> None:
        """用系统默认浏览器打开冷备或比较 HTML。"""

        filename, _ = QFileDialog.getOpenFileName(
            self, "打开 HTML 报告", filter="HTML 文件 (*.html)"
        )
        if filename and not QDesktopServices.openUrl(QUrl.fromLocalFile(filename)):
            self.statusBar().showMessage("无法打开 HTML 报告。", 5_000)

    def load_scan_config(self) -> None:
        """从 TOML 文件加载扫描并发、排除规则和摘要选项。"""

        filename, _ = QFileDialog.getOpenFileName(
            self, "加载扫描配置", filter="TOML 配置 (*.toml);;所有文件 (*)"
        )
        if not filename:
            return
        try:
            self._scan_config = load_config(Path(filename)).scan
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage(f"扫描配置加载失败：{exc}", 10_000)
            return
        self.statusBar().showMessage(
            f"已加载扫描配置：{self._scan_config.workers} 个工作线程，"
            f"{len(self._scan_config.exclude_dirs)} 条目录排除规则。",
            10_000,
        )

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
        """在状态栏显示冷备或比较扫描的实时进度。"""

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

    def _backup_completed(self, output: str) -> None:
        """显示 HTML 冷备生成完成信息。"""

        self._scan_progress_bar.hide()
        self.statusBar().showMessage(f"HTML 冷备已生成：{output}", 10_000)

    def _compare_completed(self, output: str) -> None:
        """显示 HTML 比较报告生成完成信息。"""

        self._scan_progress_bar.hide()
        self.statusBar().showMessage(f"HTML 比较报告已生成：{output}", 10_000)

    def _scan_failed(self, message: str) -> None:
        """显示冷备或比较扫描失败原因。"""

        self._scan_progress_bar.hide()
        self.statusBar().showMessage(f"扫描失败：{message}", 10_000)


def main() -> int:
    """启动 HTML 冷备图形界面。"""

    application = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return application.exec()

"""PyQt6 图形界面基础窗口。"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
)

from .config import ScanConfig, load_config
from .database import Database
from .models import ScanProgress
from .scanner import ScanController, Scanner


class ScanThread(QThread):
    """在后台线程运行扫描或恢复，避免阻塞 Qt 主事件循环。"""

    completed = pyqtSignal(str)
    progress = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        database_path: Path,
        source: Path | None,
        controller: ScanController,
        config: ScanConfig | None = None,
        resume_scan_id: str | None = None,
    ):
        super().__init__()
        self.database_path = database_path
        self.source = source
        self.config = config
        self.controller = controller
        self.resume_scan_id = resume_scan_id

    def run(self) -> None:
        """在后台调用扫描或恢复服务，并通过信号返回结果。"""

        try:
            with Database(self.database_path) as database:
                scanner = Scanner(database, self.progress.emit)
                if self.resume_scan_id is not None:
                    scanner.resume(self.resume_scan_id, self.controller)
                    self.completed.emit(self.resume_scan_id)
                    return
                if self.source is None or self.config is None:
                    raise RuntimeError("扫描线程缺少源路径或配置。")
                self.completed.emit(scanner.start(self.source, self.config, self.controller))
        except (OSError, RuntimeError, ValueError) as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    """展示项目扫描快照的非阻塞 GUI 主窗口。"""

    def __init__(self, database_path: Path | None = None):
        super().__init__()
        self.setWindowTitle("DiskHTML")
        self.resize(900, 500)
        self._database_path: Path | None = None
        self._scan_config = ScanConfig()
        self._table = QTableWidget(0, 5, self)
        self._table.setHorizontalHeaderLabels(["标识", "状态", "源路径", "已 Hash", "完成时间"])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setCentralWidget(self._table)
        self._scan_progress_bar = QProgressBar(self)
        self._scan_progress_bar.setRange(0, 0)
        self._scan_progress_bar.setTextVisible(False)
        self._scan_progress_bar.hide()
        self.statusBar().addPermanentWidget(self._scan_progress_bar)
        toolbar = QToolBar("项目", self)
        self.addToolBar(toolbar)
        open_button = QPushButton("打开项目", self)
        open_button.clicked.connect(self.open_project)
        toolbar.addWidget(open_button)
        create_button = QPushButton("新建项目", self)
        create_button.clicked.connect(self.create_project)
        toolbar.addWidget(create_button)
        scan_button = QPushButton("扫描路径", self)
        scan_button.clicked.connect(self.start_scan)
        config_button = QPushButton("\u626b\u63cf\u914d\u7f6e", self)
        config_button.clicked.connect(self.load_scan_config)
        toolbar.addWidget(config_button)
        toolbar.addWidget(scan_button)
        report_button = QPushButton("\u6253\u5f00\u62a5\u544a", self)
        report_button.clicked.connect(self.open_report)
        toolbar.addWidget(report_button)
        for label, callback in (
            ("暂停", self.pause_scan),
            ("继续", self.resume_scan),
            ("取消", self.cancel_scan),
        ):
            button = QPushButton(label, self)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        refresh_button = QPushButton("刷新", self)
        refresh_button.clicked.connect(self.refresh_project)
        toolbar.addWidget(refresh_button)
        recover_button = QPushButton("恢复任务", self)
        recover_button.clicked.connect(self.recover_selected_scan)
        toolbar.addWidget(recover_button)
        if database_path is not None:
            self.load_project(database_path)

    def create_project(self) -> None:
        """选择新路径并创建空的 SQLite 项目。"""

        filename, _ = QFileDialog.getSaveFileName(
            self, "新建项目", filter="SQLite 数据库 (*.sqlite3)"
        )
        if filename:
            path = Path(filename)
            if path.exists():
                self.statusBar().showMessage("项目文件已存在，未覆盖。", 5_000)
                return
            with Database(path):
                pass
            self.load_project(path)

    def open_project(self) -> None:
        """通过文件选择器打开已有 SQLite 项目。"""

        filename, _ = QFileDialog.getOpenFileName(
            self, "打开项目", filter="SQLite 数据库 (*.sqlite3);;所有文件 (*)"
        )
        if filename:
            self.load_project(Path(filename))

    def load_scan_config(self) -> None:
        """\u4ece TOML \u6587\u4ef6\u52a0\u8f7d\u626b\u63cf\u914d\u7f6e\u53ca\u6392\u9664\u89c4\u5219\u3002"""

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "\u52a0\u8f7d\u626b\u63cf\u914d\u7f6e",
            filter="TOML \u914d\u7f6e (*.toml);;\u6240\u6709\u6587\u4ef6 (*)",
        )
        if not filename:
            return
        try:
            self._scan_config = load_config(Path(filename)).scan
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage(f"\u914d\u7f6e\u52a0\u8f7d\u5931\u8d25\uff1a{exc}", 10_000)
            return
        self.statusBar().showMessage(
            f"\u5df2\u52a0\u8f7d\u626b\u63cf\u914d\u7f6e\uff1a{self._scan_config.workers} \u4e2a\u5de5\u4f5c\u7ebf\u7a0b\uff0c"
            f"{len(self._scan_config.exclude_dirs)} \u6761\u76ee\u5f55\u6392\u9664\u89c4\u5219\u3002",
            10_000,
        )

    def open_report(self) -> None:
        """\u9009\u62e9\u5e76\u4ea4\u7ed9\u7cfb\u7edf\u9ed8\u8ba4\u6d4f\u89c8\u5668\u6253\u5f00\u79bb\u7ebf\u62a5\u544a\u3002"""

        filename, _ = QFileDialog.getOpenFileName(
            self, "\u6253\u5f00\u79bb\u7ebf\u62a5\u544a", filter="HTML \u62a5\u544a (*.html)"
        )
        if filename and not QDesktopServices.openUrl(QUrl.fromLocalFile(filename)):
            self.statusBar().showMessage("\u65e0\u6cd5\u6253\u5f00\u62a5\u544a\u3002", 5_000)

    def start_scan(self) -> None:
        """选择目录后在后台启动扫描。"""

        if self._database_path is None:
            self.statusBar().showMessage("请先新建或打开项目。", 5_000)
            return
        source = QFileDialog.getExistingDirectory(self, "选择扫描目录")
        if not source:
            return
        if hasattr(self, "_scan_thread") and self._scan_thread.isRunning():
            self.statusBar().showMessage("已有扫描正在运行。", 5_000)
            return
        self._scan_controller = ScanController()
        self._scan_thread = ScanThread(
            self._database_path, Path(source), self._scan_controller, self._scan_config
        )
        self._scan_thread.completed.connect(self._scan_completed)
        self._scan_thread.failed.connect(self._scan_failed)
        self.statusBar().showMessage("扫描正在后台运行。")
        self._scan_thread.progress.connect(self._scan_progress)
        self._scan_progress_bar.setRange(0, 0)
        self._scan_progress_bar.show()
        self._scan_thread.start()

    def _scan_control(self, action: str) -> None:
        """向当前后台扫描发送控制请求。"""

        controller = getattr(self, "_scan_controller", None)
        if controller is None:
            self.statusBar().showMessage("当前没有运行中的扫描。", 5_000)
            return
        getattr(controller, action)()
        label = {"pause": "暂停", "resume": "继续", "cancel": "取消"}[action]
        self.statusBar().showMessage(f"已请求{label}扫描。", 5_000)

    def _selected_scan_id(self) -> str | None:
        """返回表格中当前选中的扫描任务标识。"""

        row = self._table.currentRow()
        item = self._table.item(row, 0) if row >= 0 else None
        return item.text() if item is not None else None

    def recover_selected_scan(self) -> None:
        """在后台恢复当前选中的暂停、取消或失败扫描任务。"""

        if self._database_path is None:
            self.statusBar().showMessage("请先新建或打开项目。", 5_000)
            return
        if hasattr(self, "_scan_thread") and self._scan_thread.isRunning():
            self.statusBar().showMessage("已有扫描正在运行。", 5_000)
            return
        scan_id = self._selected_scan_id()
        if scan_id is None:
            self.statusBar().showMessage("请先在任务列表中选择要恢复的扫描。", 5_000)
            return
        with Database.open_existing(self._database_path) as database:
            scan = database.get_scan(scan_id)
        if scan is None or scan["status"] not in {"PAUSED", "CANCELLED", "FAILED"}:
            self.statusBar().showMessage("只能恢复已暂停、取消或失败的扫描任务。", 5_000)
            return
        self._scan_controller = ScanController()
        self._scan_thread = ScanThread(
            self._database_path, None, self._scan_controller, resume_scan_id=scan_id
        )
        self._scan_thread.completed.connect(self._scan_completed)
        self._scan_thread.failed.connect(self._scan_failed)
        self._scan_thread.progress.connect(self._scan_progress)
        self._scan_progress_bar.setRange(0, 0)
        self._scan_progress_bar.show()
        self.statusBar().showMessage(f"正在后台恢复扫描：{scan_id}")
        self._scan_thread.start()

    def pause_scan(self) -> None:
        """请求在下一个文件边界暂停扫描。"""

        self._scan_control("pause")

    def resume_scan(self) -> None:
        """请求继续已暂停扫描。"""

        self._scan_control("resume")

    def cancel_scan(self) -> None:
        """请求取消扫描并保留已提交结果。"""

        self._scan_control("cancel")

    def _scan_progress(self, progress: ScanProgress) -> None:
        """\u5728 GUI \u4e3b\u7ebf\u7a0b\u5c55\u793a\u540e\u53f0\u626b\u63cf\u7684\u5b9e\u65f6\u5feb\u7167\u3002"""

        self._scan_progress_bar.show()
        eta_text = (
            "\u672a\u77e5"
            if progress.estimated_remaining_seconds is None
            else f"{progress.estimated_remaining_seconds:.0f} s"
        )
        self.statusBar().showMessage(
            f"\u626b\u63cf\u4e2d\uff1a{progress.files_completed}/{progress.files_seen} \u4e2a\u6587\u4ef6\uff0c"
            f"{progress.bytes_hashed / 1024 / 1024:.1f} MiB\uff0c{progress.bytes_per_second / 1024 / 1024:.1f} MiB/s\uff0c"
            f"ETA {eta_text}\uff0c{progress.current_path or ''}"
        )

    def _scan_completed(self, scan_id: str) -> None:
        """\u63a5\u6536\u540e\u53f0\u626b\u63cf\u5b8c\u6210\u4fe1\u53f7\u5e76\u5237\u65b0\u4efb\u52a1\u5217\u8868\u3002"""

        self.refresh_project()
        self._scan_progress_bar.hide()
        self.statusBar().showMessage(f"扫描已完成：{scan_id}", 10_000)

    def _scan_failed(self, message: str) -> None:
        """显示后台扫描失败的中文原因。"""

        self._scan_progress_bar.hide()
        self.statusBar().showMessage(f"扫描失败：{message}", 10_000)

    def refresh_project(self) -> None:
        """重新读取当前项目，供后台任务完成后更新列表。"""

        if self._database_path is not None:
            self.load_project(self._database_path)

    def load_project(self, path: Path) -> None:
        """读取数据库任务列表，不在界面层复制核心业务逻辑。"""

        with Database.open_existing(path) as database:
            scans = [dict(scan) for scan in database.iter_scans()]
        self._database_path = path
        self._table.setRowCount(len(scans))
        for row, scan in enumerate(scans):
            values = [
                scan["id"],
                scan["status"],
                scan["source_path"],
                str(scan["files_hashed"]),
                scan["completed_at"] or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(row, column, item)
        self.setWindowTitle(f"DiskHTML - {path}")


def main() -> int:
    """启动 GUI 事件循环。"""

    application = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return application.exec()

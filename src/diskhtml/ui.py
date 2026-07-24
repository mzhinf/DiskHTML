"""PyQt6 图形界面基础窗口。"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
)

from .config import ScanConfig
from .database import Database
from .scanner import Scanner


class ScanThread(QThread):
    """在后台线程运行扫描，避免阻塞 Qt 主事件循环。"""

    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, database_path: Path, source: Path):
        super().__init__()
        self.database_path = database_path
        self.source = source

    def run(self) -> None:
        """调用既有扫描服务并通过信号返回结果。"""

        try:
            with Database(self.database_path) as database:
                self.completed.emit(Scanner(database).start(self.source, ScanConfig()))
        except (OSError, RuntimeError, ValueError) as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    """展示项目扫描快照的非阻塞 GUI 主窗口。"""

    def __init__(self, database_path: Path | None = None):
        super().__init__()
        self.setWindowTitle("DiskHTML")
        self.resize(900, 500)
        self._database_path: Path | None = None
        self._table = QTableWidget(0, 5, self)
        self._table.setHorizontalHeaderLabels(["标识", "状态", "源路径", "已 Hash", "完成时间"])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setCentralWidget(self._table)
        toolbar = QToolBar("项目", self)
        self.addToolBar(toolbar)
        open_button = QPushButton("打开项目", self)
        open_button.clicked.connect(self.open_project)
        toolbar.addWidget(open_button)
        create_button = QPushButton("新建项目", self)
        create_button.clicked.connect(self.create_project)
        toolbar.addWidget(create_button)
        refresh_button = QPushButton("刷新", self)
        refresh_button.clicked.connect(self.refresh_project)
        toolbar.addWidget(refresh_button)
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

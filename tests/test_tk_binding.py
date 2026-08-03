"""Tkinter 依赖和导入契约测试。"""

from __future__ import annotations

import tkinter
import tomllib
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parents[1]


class TkBindingTests(unittest.TestCase):
    """确保桌面外壳只使用 Python 标准库 Tkinter。"""

    def test_project_has_no_qt_runtime_dependency(self) -> None:
        """运行依赖不得重新引入 PySide6、PyQt6 或其他 Qt 绑定。"""

        project = tomllib.loads((_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = project["project"]["dependencies"]
        self.assertFalse(any("pyside" in item.casefold() for item in dependencies))
        self.assertFalse(any("pyqt" in item.casefold() for item in dependencies))

    def test_ui_uses_tkinter_without_qt_imports(self) -> None:
        """桌面界面必须使用 tkinter/ttk 且不含 Qt 导入。"""

        source = (_PROJECT_ROOT / "src" / "diskhtml" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("import tkinter as tk", source)
        self.assertIn("from tkinter import filedialog, ttk", source)
        self.assertNotIn("PySide6", source)
        self.assertNotIn("PyQt6", source)
        self.assertNotIn("QThread", source)
        self.assertIsNotNone(tkinter.Tk)
        self.assertIsNotNone(tkinter.ttk.Notebook)

    def test_build_script_does_not_use_qt_for_icons(self) -> None:
        """构建过程必须直接使用固定 ICO，而不是调用 QtSvg。"""

        source = (_PROJECT_ROOT / "scripts" / "build_windows.py").read_text(encoding="utf-8")
        self.assertIn('assets / "folder-tree.ico"', source)
        self.assertNotIn("PySide6", source)
        self.assertNotIn("QSvgRenderer", source)


if __name__ == "__main__":
    unittest.main()

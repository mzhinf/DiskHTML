"""PyInstaller 入口分流测试。"""

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch


def _load_entry_module():
    """按脚本路径加载 GUI 打包入口，避免依赖包安装方式。"""

    path = Path(__file__).parents[1] / "scripts" / "gui_entry.py"
    spec = importlib.util.spec_from_file_location("diskhtml_gui_entry_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GuiEntryTests(TestCase):
    """验证带参数的 DiskHTML.exe 会执行 HTML 命令而非只启动 GUI。"""

    def test_arguments_dispatch_to_command_entry(self) -> None:
        """用户输入 snapshot 参数时应进入精简命令行入口。"""

        entry = _load_entry_module()
        with (
            patch.object(entry, "command_main", return_value=0) as command_main,
            patch.object(entry, "gui_main", return_value=0) as gui_main,
        ):
            self.assertEqual(entry.main(["snapshot", "F:\\Documents", ".\\资料快照.html"]), 0)

        command_main.assert_called_once_with(["snapshot", "F:\\Documents", ".\\资料快照.html"])
        gui_main.assert_not_called()

    def test_backup_argument_generates_html_through_entry(self) -> None:
        """打包入口的 snapshot 参数应实际生成 HTML，而不是启动 GUI。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "backup.html"
            source.mkdir()
            (source / "sample.txt").write_text("内容", encoding="utf-8")

            self.assertEqual(_load_entry_module().main(["snapshot", str(source), str(output)]), 0)
            self.assertTrue(output.is_file())

    def test_no_arguments_dispatch_to_gui(self) -> None:
        """双击 EXE 时应仍启动图形界面。"""

        entry = _load_entry_module()
        with (
            patch.object(entry, "command_main", return_value=0) as command_main,
            patch.object(entry, "gui_main", return_value=0) as gui_main,
        ):
            self.assertEqual(entry.main([]), 0)

        gui_main.assert_called_once_with()
        command_main.assert_not_called()

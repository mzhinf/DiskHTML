"""发布 ZIP 验证器测试。"""

from __future__ import annotations

import runpy
import tempfile
import zipfile
from pathlib import Path
from unittest import TestCase


class ReleaseVerificationScriptTests(TestCase):
    """不启动打包程序即可验证归档安全和运行时结构门禁。"""

    @classmethod
    def setUpClass(cls) -> None:
        """加载验证辅助函数，不执行命令行入口。"""

        project_root = Path(__file__).parent.parent
        cls.verifier = runpy.run_path(str(project_root / "scripts" / "verify_release.py"))

    def test_archive_member_validation_rejects_parent_traversal(self) -> None:
        """恶意父目录条目必须在解压前被拒绝。"""

        validate = self.verifier["_validate_archive_members"]
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "unsafe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../outside.txt", "unsafe")

            with zipfile.ZipFile(archive_path) as archive:
                with self.assertRaises(ValueError):
                    validate(archive)

    def test_archive_member_validation_accepts_release_layout(self) -> None:
        """正常 DiskHTML 顶层目录结构必须通过路径检查。"""

        validate = self.verifier["_validate_archive_members"]
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "release.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("DiskHTML/DiskHTML.exe", b"exe")
                archive.writestr("DiskHTML/_internal/python312.dll", b"dll")

            with zipfile.ZipFile(archive_path) as archive:
                validate(archive)

    def test_runtime_layout_requires_tkinter_files(self) -> None:
        """缺少 Tcl/Tk DLL 或数据目录的发布包必须失败。"""

        validate = self.verifier["_validate_runtime_layout"]
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            internal = package / "_internal"
            internal.mkdir()
            (internal / "python312.dll").write_bytes(b"python")
            with self.assertRaises(RuntimeError):
                validate(package)

    def test_runtime_layout_accepts_tkinter_and_rejects_qt(self) -> None:
        """完整 Tkinter 包可通过，但任何残留 Qt 目录必须阻断。"""

        validate = self.verifier["_validate_runtime_layout"]
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            internal = package / "_internal"
            internal.mkdir()
            for name in ("python312.dll", "_tkinter.pyd", "tcl86t.dll", "tk86t.dll"):
                (internal / name).write_bytes(b"runtime")
            (internal / "_tcl_data").mkdir()
            (internal / "_tk_data").mkdir()
            validate(package)

            qt = internal / "PySide6"
            qt.mkdir()
            (qt / "Qt6Core.dll").write_bytes(b"qt")
            with self.assertRaises(RuntimeError):
                validate(package)

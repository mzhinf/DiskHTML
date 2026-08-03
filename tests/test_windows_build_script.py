"""Windows EXE 发布构建脚本测试。"""

from __future__ import annotations

import runpy
import tempfile
from pathlib import Path
from unittest import TestCase


class WindowsBuildScriptTests(TestCase):
    """验证 Python 构建器与可选 PowerShell 包装器约定。"""

    @classmethod
    def setUpClass(cls) -> None:
        """加载构建辅助函数，不执行命令行入口。"""

        cls.project_root = Path(__file__).parent.parent
        cls.builder_path = cls.project_root / "scripts" / "build_windows.py"
        cls.builder = runpy.run_path(str(cls.builder_path))

    def test_python_builder_creates_onedir_release_zip(self) -> None:
        """主构建器必须打包完整 onedir 运行时。"""

        script = self.builder_path.read_text(encoding="utf-8")
        self.assertIn('"--onedir"', script)
        self.assertNotIn('"--onefile"', script)
        self.assertIn('package / "_internal"', script)
        self.assertIn('"DiskHTML-win-x64.zip"', script)
        self.assertIn("zipfile.ZipFile", script)
        self.assertIn('"--icon"', script)
        self.assertIn('"--add-data"', script)
        self.assertIn('assets / "folder-tree.ico"', script)
        self.assertNotIn("PySide6", script)
        self.assertNotIn("QSvgRenderer", script)

    def test_version_resource_is_derived_from_project_metadata(self) -> None:
        """构建版本资源必须与唯一项目版本源保持一致。"""

        project_version = self.builder["read_project_version"](self.project_root)
        with tempfile.TemporaryDirectory() as temporary:
            resource = self.builder["write_windows_version_resource"](
                Path(temporary) / "version-info.txt", project_version
            )
            content = resource.read_text(encoding="utf-8")
        self.assertEqual("1.0.0", project_version)
        self.assertIn("FileVersion', '1.0.0'", content)
        self.assertIn("filevers=(1, 0, 0, 0)", content)

    def test_prebuilt_icon_assets_are_available(self) -> None:
        """SVG 源文件及 Tk/Windows 使用的 PNG、ICO 派生资源必须完整。"""

        assets = self.project_root / "src" / "diskhtml" / "assets"
        svg_expected = {"folder-tree.svg", "folders.svg", "git-compare.svg", "database.svg"}
        raster_expected = {"folder-tree.ico", "folders.png", "git-compare.png", "database.png"}
        self.assertEqual(svg_expected, {path.name for path in assets.glob("*.svg")})
        self.assertTrue(
            raster_expected <= {path.name for path in assets.iterdir() if path.is_file()}
        )
        for name in raster_expected:
            self.assertGreater((assets / name).stat().st_size, 0)

    def test_powershell_is_only_an_optional_wrapper(self) -> None:
        """PowerShell 入口必须把全部构建工作转交给 Python 构建器。"""

        wrapper = (self.project_root / "scripts" / "build_windows.ps1").read_text(encoding="utf-8")
        self.assertIn('"build_windows.py"', wrapper)
        self.assertNotIn("PyInstaller", wrapper)
        self.assertNotIn("Compress-Archive", wrapper)
        self.assertNotIn("Remove-Item", wrapper)

    def test_github_workflow_builds_with_project_virtual_environment(self) -> None:
        """Windows CI 必须创建并使用与本地构建相同的 .venv 约定。"""

        workflow = (self.project_root / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("python -m venv .venv", workflow)
        self.assertIn(".venv\\Scripts\\python.exe scripts\\build_windows.py --clean", workflow)
        self.assertIn(".venv\\Scripts\\python.exe scripts\\verify_release.py", workflow)

    def test_cleanup_rejects_paths_outside_build_directory(self) -> None:
        """路径计算错误绝不能删除构建目录外的内容。"""

        remove_generated = self.builder["_remove_generated"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_root = root / "build"
            build_root.mkdir()
            outside = root / "keep.txt"
            outside.write_text("keep", encoding="utf-8")

            with self.assertRaises(ValueError):
                remove_generated(outside, build_root)

            self.assertEqual("keep", outside.read_text(encoding="utf-8"))

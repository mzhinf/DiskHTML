"""Windows EXE 发布包构建脚本测试。"""

from pathlib import Path
from unittest import TestCase


class WindowsBuildScriptTests(TestCase):
    """验证发布脚本明确生成含完整运行库的目录式 EXE 压缩包。"""

    def test_script_builds_onedir_and_packages_complete_runtime(self) -> None:
        """脚本应把 DiskHTML.exe 与 _internal 一起压缩为发布 ZIP。"""

        project_root = Path(__file__).parent.parent
        script = (project_root / "scripts" / "build_windows.ps1").read_text(encoding="utf-8")

        self.assertIn('"--onedir"', script)
        self.assertNotIn('"--onefile"', script)
        self.assertIn('$package = Join-Path $dist "DiskHTML"', script)
        self.assertIn('$outputExecutable = Join-Path $package "DiskHTML.exe"', script)
        self.assertIn('$internalDirectory = Join-Path $package "_internal"', script)
        self.assertIn('$releaseArchive = Join-Path $releaseRoot "DiskHTML-win-x64.zip"', script)
        self.assertIn("Compress-Archive -LiteralPath $package", script)
        self.assertIn("缺少运行库目录", script)

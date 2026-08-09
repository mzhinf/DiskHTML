"""冻结 EXE 默认配置复制测试。"""

from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from diskhtml._exe_config import ensure_exe_config


class ExeConfigTests(TestCase):
    """验证内置模板首次复制且不会覆盖用户配置。"""

    @classmethod
    def setUpClass(cls) -> None:
        """读取仓库中的唯一配置示例作为测试输入。"""

        cls.example = Path(__file__).parents[1] / "config.example.toml"

    def _package(self, root: Path, *, include_template: bool = True) -> tuple[Path, Path]:
        """创建最小 onedir 路径并返回 EXE 与运行时目录。"""

        package = root / "DiskHTML"
        runtime = package / "_internal"
        package.mkdir()
        executable = package / "DiskHTML.exe"
        executable.write_bytes(b"exe")
        if include_template:
            template = runtime / "config" / self.example.name
            template.parent.mkdir(parents=True)
            shutil.copyfile(self.example, template)
        else:
            runtime.mkdir()
        return executable, runtime

    def test_first_start_copies_packaged_template_beside_executable(self) -> None:
        """首次启动应生成与内置模板逐字节一致的 config.toml。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            executable, runtime = self._package(Path(directory))
            config = ensure_exe_config(executable=executable, runtime_root=runtime)

            self.assertEqual(executable.parent / "config.toml", config)
            self.assertEqual(self.example.read_bytes(), config.read_bytes())

    def test_existing_external_config_is_not_overwritten(self) -> None:
        """后续启动必须保留用户修改后的外部配置。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            executable, runtime = self._package(Path(directory))
            config = ensure_exe_config(executable=executable, runtime_root=runtime)
            original = config.read_text(encoding="utf-8")
            customized = f"{original}\n# 用户保留的自定义标记。\n"
            config.write_text(customized, encoding="utf-8")

            self.assertEqual(
                config,
                ensure_exe_config(executable=executable, runtime_root=runtime),
            )
            self.assertEqual(customized, config.read_text(encoding="utf-8"))

    def test_missing_packaged_template_is_rejected(self) -> None:
        """发布包缺少内置模板时不得静默使用内建默认值。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            executable, runtime = self._package(Path(directory), include_template=False)
            with self.assertRaises(FileNotFoundError):
                ensure_exe_config(executable=executable, runtime_root=runtime)

    def test_source_execution_does_not_create_config(self) -> None:
        """非冻结源码入口应保留原有无默认文件行为。"""

        with patch("diskhtml._exe_config.sys.frozen", False, create=True):
            self.assertIsNone(ensure_exe_config())

"""产品版本唯一来源与运行时读取测试。"""

from __future__ import annotations

import tomllib
from pathlib import Path
from unittest import TestCase

from diskhtml import __version__
from diskhtml.version import get_version


class VersionTests(TestCase):
    """验证产品版本只由 pyproject.toml 定义。"""

    def test_runtime_version_matches_project_metadata(self) -> None:
        """源码运行时必须读取 pyproject.toml 的 project.version。"""

        project_root = Path(__file__).parent.parent
        with (project_root / "pyproject.toml").open("rb") as handle:
            expected = tomllib.load(handle)["project"]["version"]
        self.assertEqual(expected, __version__)
        self.assertEqual(expected, get_version())
        self.assertIsInstance(expected, str)
        self.assertEqual(expected, expected.strip())
        self.assertTrue(expected)

    def test_package_init_no_longer_contains_a_literal_version(self) -> None:
        """包入口只重导出版本，避免形成第二个手工版本来源。"""

        content = (Path(__file__).parent.parent / "src" / "diskhtml" / "__init__.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from .version import __version__", content)
        self.assertNotIn('__version__ = "', content)

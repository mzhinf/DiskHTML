"""源码文本编码回归测试。"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

_SOURCE_ROOT = Path(__file__).parents[1] / "src" / "diskhtml"
_CORRUPTED_TEXT = re.compile(r"\?{3,}|\ufffd")


class SourceTextEncodingTests(unittest.TestCase):
    """防止损坏的中文文本再次进入源码和构建产物。"""

    def test_python_sources_are_valid_utf8(self) -> None:
        """所有 Python 源码都必须能够按 UTF-8 严格解码。"""

        failures: list[str] = []
        for path in sorted(_SOURCE_ROOT.rglob("*.py")):
            try:
                path.read_text(encoding="utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                failures.append(f"{path.relative_to(_SOURCE_ROOT)}: {exc}")

        self.assertEqual([], failures)

    def test_string_literals_do_not_contain_corruption_markers(self) -> None:
        """字符串常量中不得出现连续问号或 Unicode 替换字符。"""

        failures: list[str] = []
        for path in sorted(_SOURCE_ROOT.rglob("*.py")):
            source = path.read_text(encoding="utf-8", errors="strict")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                if _CORRUPTED_TEXT.search(node.value):
                    failures.append(f"{path.relative_to(_SOURCE_ROOT)}:{node.lineno}")

        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()

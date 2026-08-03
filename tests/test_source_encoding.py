"""Source encoding and file-level description regression tests."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parents[1]
_SOURCE_ROOT = _PROJECT_ROOT / "src" / "diskhtml"
_PYTHON_ROOTS = (_PROJECT_ROOT / "src", _PROJECT_ROOT / "scripts", _PROJECT_ROOT / "tests")
_CORRUPTED_TEXT = re.compile(r"\?{3,}|\ufffd")


def _python_files() -> list[Path]:
    """Return every first-party Python source, maintenance script, and test file."""

    return sorted(path for root in _PYTHON_ROOTS for path in root.rglob("*.py"))


class SourceTextEncodingTests(unittest.TestCase):
    """Prevent damaged text or undocumented code files from entering a release."""

    def test_python_sources_are_valid_utf8(self) -> None:
        """Every first-party Python file must decode strictly as UTF-8."""

        failures: list[str] = []
        for path in _python_files():
            try:
                path.read_text(encoding="utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                failures.append(f"{path.relative_to(_PROJECT_ROOT)}: {exc}")

        self.assertEqual([], failures)

    def test_python_files_have_module_descriptions(self) -> None:
        """Every first-party Python file must explain its purpose in a module docstring."""

        failures: list[str] = []
        for path in _python_files():
            source = path.read_text(encoding="utf-8", errors="strict")
            if not ast.get_docstring(ast.parse(source, filename=str(path))):
                failures.append(str(path.relative_to(_PROJECT_ROOT)))

        self.assertEqual([], failures)

    def test_powershell_files_have_header_descriptions(self) -> None:
        """Every first-party PowerShell file must start with a purpose comment."""

        failures: list[str] = []
        for path in sorted((_PROJECT_ROOT / "scripts").rglob("*.ps1")):
            first_line = path.read_text(encoding="utf-8", errors="strict").splitlines()[0]
            if not first_line.startswith("# "):
                failures.append(str(path.relative_to(_PROJECT_ROOT)))

        self.assertEqual([], failures)

    def test_github_workflows_have_header_descriptions(self) -> None:
        """Every first-party GitHub workflow must start with a purpose comment."""

        failures: list[str] = []
        workflow_root = _PROJECT_ROOT / ".github" / "workflows"
        for path in sorted([*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")]):
            first_line = path.read_text(encoding="utf-8", errors="strict").splitlines()[0]
            if not first_line.startswith("# "):
                failures.append(str(path.relative_to(_PROJECT_ROOT)))

        self.assertEqual([], failures)

    def test_string_literals_do_not_contain_corruption_markers(self) -> None:
        """String constants must not contain repeated question marks or replacement characters."""

        failures: list[str] = []
        for path in _python_files():
            source = path.read_text(encoding="utf-8", errors="strict")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                if _CORRUPTED_TEXT.search(node.value):
                    failures.append(f"{path.relative_to(_PROJECT_ROOT)}:{node.lineno}")

        self.assertEqual([], failures)

    def test_readable_source_text_uses_direct_utf8(self) -> None:
        """Readable text uses UTF-8; only protocol or security escapes are allowed."""

        allowed = {
            "archive_ui.py": {"feff"},
            "html_archive.py": {"0026", "003c", "003e"},
        }
        unicode_escape = re.compile(r"\\u([0-9a-fA-F]{4})")
        failures: list[str] = []
        for path in sorted(_SOURCE_ROOT.rglob("*.py")):
            source = path.read_text(encoding="utf-8", errors="strict")
            permitted = allowed.get(path.name, set())
            for lineno, line in enumerate(source.splitlines(), 1):
                for match in unicode_escape.finditer(line):
                    if match.group(1).lower() not in permitted:
                        failures.append(
                            f"{path.relative_to(_SOURCE_ROOT)}:{lineno}:{match.group(0)}"
                        )

        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()

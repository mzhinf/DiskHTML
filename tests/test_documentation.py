"""Repository documentation index and architecture consistency tests."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parents[1]
_DOCS_ROOT = _PROJECT_ROOT / "docs"


class DocumentationTests(unittest.TestCase):
    """Keep public documentation synchronized with the repository layout."""

    def test_document_index_lists_every_markdown_document(self) -> None:
        """Every maintained Markdown document must appear in the document table."""

        index = (_DOCS_ROOT / "README.md").read_text(encoding="utf-8")
        documents = [
            *(
                _PROJECT_ROOT / name
                for name in (
                    "README.md",
                    "README.en.md",
                    "CONTRIBUTING.md",
                    "SECURITY.md",
                    "CHANGELOG.md",
                    "THIRD_PARTY_NOTICES.md",
                )
            ),
            *(path for path in _DOCS_ROOT.glob("*.md") if path.name != "README.md"),
        ]
        missing = [path.name for path in sorted(documents) if path.name not in index]
        self.assertEqual([], missing)

    def test_architecture_table_lists_first_party_runtime_modules(self) -> None:
        """Every non-package-marker runtime module must be represented in architecture docs."""

        architecture = (_DOCS_ROOT / "architecture.md").read_text(encoding="utf-8")
        source_root = _PROJECT_ROOT / "src" / "diskhtml"
        modules = [path for path in source_root.rglob("*.py") if path.name != "__init__.py"]
        missing = [
            str(path.relative_to(_PROJECT_ROOT)).replace("\\", "/")
            for path in sorted(modules)
            if path.name not in architecture
        ]
        self.assertEqual([], missing)

    def test_local_markdown_links_resolve(self) -> None:
        """Every relative Markdown link must point to an existing repository file."""

        failures: list[str] = []
        markdown_files = sorted([*_DOCS_ROOT.glob("*.md"), *_PROJECT_ROOT.glob("*.md")])
        link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for document in markdown_files:
            for target in link_pattern.findall(document.read_text(encoding="utf-8")):
                target = target.strip().strip("<>").split("#", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                if not (document.parent / target).resolve().exists():
                    failures.append(f"{document.relative_to(_PROJECT_ROOT)} -> {target}")
        self.assertEqual([], failures)

    def test_markdown_does_not_contain_encoded_newline_artifacts(self) -> None:
        """Documentation must not contain shell-escaped newlines as visible text."""

        failures: list[str] = []
        for path in sorted([*_DOCS_ROOT.glob("*.md"), *_PROJECT_ROOT.glob("*.md")]):
            if "\\n\\n" in path.read_text(encoding="utf-8"):
                failures.append(str(path.relative_to(_PROJECT_ROOT)))
        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()

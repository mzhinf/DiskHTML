"""单文件 HTML 快照与比较报告测试。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from diskhtml.config import ScanConfig
from diskhtml.html_archive import (
    compare_html_archives,
    compare_html_directory_to_source,
    create_html_snapshot,
    html_snapshot_directories,
    read_html_snapshot,
    render_html_snapshot_from_sqlite,
    sqlite_snapshot_path,
)


class HtmlArchiveTests(TestCase):
    """验证用户交付物是单个可视化 HTML，而不是 SQLite 项目文件。"""

    def test_backup_and_compare_are_visual_single_html_files(self) -> None:
        """快照可被读取和比较，且包含离线可视化所需的交互元素。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            old_source = root / "old"
            new_source = root / "new"
            old_source.mkdir()
            new_source.mkdir()
            (old_source / "same.txt").write_text("相同", encoding="utf-8")
            (old_source / "changed.txt").write_text("旧内容", encoding="utf-8")
            (old_source / "missing.txt").write_text("仅旧侧", encoding="utf-8")
            (new_source / "same.txt").write_text("相同", encoding="utf-8")
            (new_source / "changed.txt").write_text("新内容", encoding="utf-8")
            (new_source / "added.txt").write_text("仅新侧", encoding="utf-8")

            options = ScanConfig(workers=1, queue_size=1)
            old_archive = create_html_snapshot(old_source, root / "old.html", options)
            new_archive = create_html_snapshot(new_source, root / "new.html", options)
            comparison = compare_html_archives(old_archive, new_archive, root / "compare.html")

            payload = read_html_snapshot(old_archive)
            archive_text = old_archive.read_text(encoding="utf-8")
            comparison_text = comparison.read_text(encoding="utf-8")
            comparison_exists = comparison.is_file()

        self.assertEqual(payload["kind"], "scan")
        self.assertEqual(payload["statistics"]["total_files"], 3)
        self.assertIn('id="tree"', archive_text)
        self.assertIn("renderTree()", archive_text)
        self.assertIn("SHA-256", archive_text)
        self.assertIn('class="explorer"', archive_text)
        self.assertIn('class="tree-pane"', archive_text)
        self.assertIn('id="columns"', archive_text)
        self.assertIn("makeSortButton", archive_text)
        self.assertIn('id="details-toggle"', archive_text)
        self.assertIn('id="export-view"', archive_text)
        self.assertIn("appendHighlighted", archive_text)
        self.assertIn("matchesSearch", archive_text)
        self.assertIn("search.startsWith('sha:')", archive_text)
        self.assertIn("fileUrl", archive_text)
        self.assertIn("status-added", comparison_text)
        self.assertIn("generatedAt", archive_text)
        self.assertIn("\u72b6\u6001", comparison_text)
        self.assertIn("\u72b6\u6001", comparison_text)
        self.assertIn('id="filter"', archive_text)
        self.assertIn('id="rows"', archive_text)
        self.assertIn("显示更多", archive_text)
        self.assertNotIn("transient-index.sqlite3", archive_text)
        self.assertIn("\u72b6\u6001", comparison_text)
        self.assertIn('"CHANGED":1', comparison_text)
        self.assertIn('"ADDED":1', comparison_text)
        self.assertIn('"MISSING":1', comparison_text)
        self.assertIn('id="same-heading"', comparison_text)
        self.assertNotIn('id="sources"', comparison_text)
        self.assertNotIn("data-status=", comparison_text)
        self.assertNotIn('id="sources"', comparison_text)
        self.assertNotIn("data-status=", comparison_text)
        self.assertTrue(comparison_exists)

    def test_selected_html_directory_compares_to_local_directory(self) -> None:
        """快照树中选定的目录应重定根后与本机目录比较。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            historical = root / "historical"
            current = root / "current"
            historical.mkdir()
            current.mkdir()
            (historical / "selected").mkdir()
            (historical / "selected" / "same.txt").write_text("相同", encoding="utf-8")
            (historical / "selected" / "changed.txt").write_text("旧内容", encoding="utf-8")
            (historical / "outside.txt").write_text("不参与比较", encoding="utf-8")
            (current / "same.txt").write_text("相同", encoding="utf-8")
            (current / "changed.txt").write_text("新内容", encoding="utf-8")
            (current / "added.txt").write_text("新增", encoding="utf-8")
            archive = create_html_snapshot(
                historical, root / "historical.html", ScanConfig(workers=1, queue_size=1)
            )
            comparison = compare_html_directory_to_source(
                archive,
                "selected",
                current,
                root / "comparison.html",
                ScanConfig(workers=1, queue_size=1),
            )
            text = comparison.read_text(encoding="utf-8")
            directories = html_snapshot_directories(archive)

        self.assertIn("selected", directories)
        self.assertIn('"selected_directory":"selected"', text)
        self.assertIn('"MATCH":1', text)
        self.assertIn('"CHANGED":1', text)
        self.assertIn('"ADDED":1', text)
        self.assertIn("<td>ADDED</td>", text)
        self.assertIn("<td>ADDED</td>", text)
        self.assertNotIn("outside.txt", text)

    def test_backup_rejects_non_html_or_existing_output(self) -> None:
        """用户交付物必须是新建的 .html 文件，避免覆盖既有快照。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            with self.assertRaisesRegex(ValueError, ".html"):
                create_html_snapshot(source, root / "archive.sqlite3")
            output = create_html_snapshot(
                source, root / "archive.html", ScanConfig(workers=1, queue_size=1)
            )
            sqlite_output = sqlite_snapshot_path(output)
            rebuilt = render_html_snapshot_from_sqlite(sqlite_output, root / "rebuilt.html")
            self.assertTrue(sqlite_output.is_file())
            self.assertIn('id="tree"', rebuilt.read_text(encoding="utf-8"))
            with self.assertRaises(FileExistsError):
                create_html_snapshot(source, output, ScanConfig(workers=1, queue_size=1))

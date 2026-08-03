"""单文件 HTML 快照与比较报告测试。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from diskhtml import __version__, html_archive
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
        self.assertEqual(payload["generator"], {"name": "DiskHTML", "version": __version__})
        self.assertIsInstance(payload["volume"], dict)
        self.assertTrue(
            {"disk_model", "disk_serial", "volume_guid", "total_bytes"} <= set(payload["volume"])
        )
        self.assertEqual(payload["statistics"]["total_files"], 3)
        self.assertIn('id="report-title"', archive_text)
        self.assertIn('id="report-version"', archive_text)
        self.assertIn(
            f'id="report-version" class="report-version">DiskHTML v{__version__}</span>'
            '<span id="report-name"> - ',
            archive_text,
        )
        self.assertNotIn('id="generator-version"', archive_text)
        self.assertIn('id="tree"', archive_text)
        self.assertIn("renderTree()", archive_text)
        self.assertIn("SHA-256", archive_text)
        self.assertIn('class="explorer"', archive_text)
        self.assertIn('class="snapshot-icon lucide lucide-hard-drive-icon', archive_text)
        self.assertIn('<path d="M2.212 11.577', archive_text)
        self.assertIn("entryTypeIcon", archive_text)
        self.assertIn("entry-type-icon", archive_text)
        self.assertIn("treeFolderIcon", archive_text)
        self.assertIn("lucide-folder-open-icon", archive_text)
        self.assertIn(
            "m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20",
            archive_text,
        )
        self.assertIn(
            "const icon=treeFolderIcon(expanded&&(isRoot||hasChildren))",
            archive_text,
        )
        self.assertIn(
            "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9",
            archive_text,
        )
        self.assertIn(
            "M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8",
            archive_text,
        )
        self.assertIn("M14 2v5a1 1 0 0 0 1 1h5", archive_text)
        self.assertIn("const icon=entryTypeIcon(row.kind)", archive_text)
        self.assertNotIn("icon.textContent=row.kind", archive_text)
        self.assertNotIn("📁", archive_text)
        self.assertNotIn("▧", archive_text)
        self.assertIn('id="disk-summary"', archive_text)
        self.assertIn("硬盘 ID：", archive_text)
        self.assertIn('class="tree-pane"', archive_text)
        self.assertIn('id="columns"', archive_text)
        self.assertIn("makeSortButton", archive_text)
        self.assertIn('id="details-toggle"', archive_text)
        self.assertIn('id="language-toggle"', archive_text)
        self.assertIn("const messages = {", archive_text)
        self.assertIn("function applyLanguage(next)", archive_text)
        self.assertIn("Switch to Chinese", archive_text)
        self.assertIn("statusLabel(row.status)", comparison_text)
        self.assertIn('id="export-view"', archive_text)
        self.assertIn("appendHighlighted", archive_text)
        self.assertIn("matchesSearch", archive_text)
        self.assertIn("search.startsWith('sha:')", archive_text)
        self.assertIn("fileUrl", archive_text)
        self.assertIn("status-added", comparison_text)
        self.assertIn("generatedAt", archive_text)
        self.assertIn("snapshotTime", archive_text)
        self.assertIn(".tree-folder-icon{display:block", archive_text)
        self.assertNotIn("folder-icon::before", archive_text)
        self.assertNotIn("className='folder-icon'", archive_text)
        self.assertIn(".tree-row:hover{background:#e8e8e8}", archive_text)
        self.assertIn(".tree-row.active{background:#cce8ff}", archive_text)
        self.assertIn(".tree-toggle::before", archive_text)
        self.assertIn(".tree-toggle[aria-expanded='true']::before", archive_text)
        self.assertIn(".tree-branch{visibility:hidden}", archive_text)
        self.assertNotIn("border-left:1px dotted", archive_text)
        self.assertNotIn("tree-node::before", archive_text)
        self.assertIn("height:calc(100vh - 24px)", archive_text)
        self.assertIn("height:33px;min-height:33px;max-height:33px", archive_text)
        self.assertIn("toggle.textContent=''", archive_text)
        self.assertIn("row.className='tree-row'+", archive_text)
        self.assertIn("className='tree-node'", archive_text)
        self.assertIn("className='tree-toggle'", archive_text)
        self.assertNotIn("createElement('details')", archive_text)
        self.assertNotIn('class="tree-title"', archive_text)
        self.assertIn("状态", comparison_text)
        self.assertIn('id="filter"', archive_text)
        self.assertIn('id="rows"', archive_text)
        self.assertIn("显示更多", archive_text)
        self.assertNotIn("transient-index.sqlite3", archive_text)
        self.assertIn('"CHANGED":1', comparison_text)
        self.assertIn('"ADDED":1', comparison_text)
        self.assertIn('"MISSING":1', comparison_text)
        self.assertIn('"left_volume":', comparison_text)
        self.assertIn('"right_volume":', comparison_text)
        self.assertIn('id="same-heading"', comparison_text)
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

    def test_comparison_fallback_rows_use_available_side_metadata(self) -> None:
        """静态回退表格应为新增和缺失条目选择存在一侧的详情。"""

        rows = html_archive._initial_table_rows(
            {
                "kind": "compare",
                "entries": [
                    {
                        "relative_path": "only-old.txt",
                        "old_size_bytes": 2048,
                        "old_modified_time": "旧修改时间",
                        "old_created_time": "旧创建时间",
                        "old_sha256": "OLD",
                        "new_size_bytes": None,
                        "status": "MISSING",
                    },
                    {
                        "relative_path": "only-new.txt",
                        "old_size_bytes": None,
                        "new_size_bytes": 3072,
                        "new_modified_time": "新修改时间",
                        "new_created_time": "新创建时间",
                        "new_sha256": "NEW",
                        "status": "ADDED",
                    },
                ],
            }
        )

        self.assertIn("<td>only-old.txt</td><td>2.0 KB</td><td>旧修改时间</td>", rows)
        self.assertIn("<td>OLD</td><td>MISSING</td>", rows)
        self.assertIn("<td>only-new.txt</td><td>3.0 KB</td><td>新修改时间</td>", rows)
        self.assertIn("<td>NEW</td><td>ADDED</td>", rows)

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

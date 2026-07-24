"""单文件 HTML 冷备与比较报告测试。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from diskhtml.config import ScanConfig
from diskhtml.html_archive import compare_html_archives, create_html_backup, read_html_backup


class HtmlArchiveTests(TestCase):
    """验证用户交付物是单个可视化 HTML，而不是 SQLite 项目文件。"""

    def test_backup_and_compare_are_visual_single_html_files(self) -> None:
        """冷备快照可被读取和比较，且包含离线可视化所需的交互元素。"""

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
            old_archive = create_html_backup(old_source, root / "old.html", options)
            new_archive = create_html_backup(new_source, root / "new.html", options)
            comparison = compare_html_archives(old_archive, new_archive, root / "compare.html")

            payload = read_html_backup(old_archive)
            archive_text = old_archive.read_text(encoding="utf-8")
            comparison_text = comparison.read_text(encoding="utf-8")
            comparison_exists = comparison.is_file()

        self.assertEqual(payload["kind"], "scan")
        self.assertEqual(payload["statistics"]["total_files"], 3)
        self.assertIn('id="filter"', archive_text)
        self.assertIn('id="rows"', archive_text)
        self.assertIn("显示更多", archive_text)
        self.assertNotIn("transient-index.sqlite3", archive_text)
        self.assertIn('"MATCH":1', comparison_text)
        self.assertIn('"CHANGED":1', comparison_text)
        self.assertIn('"ADDED":1', comparison_text)
        self.assertIn('"MISSING":1', comparison_text)
        self.assertIn('data-status="CHANGED"', comparison_text)
        self.assertTrue(comparison_exists)

    def test_backup_rejects_non_html_or_existing_output(self) -> None:
        """用户交付物必须是新建的 .html 文件，避免覆盖既有冷备。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            with self.assertRaisesRegex(ValueError, ".html"):
                create_html_backup(source, root / "archive.sqlite3")
            output = create_html_backup(
                source, root / "archive.html", ScanConfig(workers=1, queue_size=1)
            )
            with self.assertRaises(FileExistsError):
                create_html_backup(source, output, ScanConfig(workers=1, queue_size=1))

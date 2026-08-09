"""命令行帮助和数据库维护命令测试。"""

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from diskhtml.cli import main
from diskhtml.html_archive import read_html_snapshot
from diskhtml.sampled_hash import sampled_sha256_algorithm


class CliTests(TestCase):
    """验证可安装入口的最小闭环。"""

    def test_no_command_prints_help(self) -> None:
        """不带子命令时应显示中文帮助并成功退出。"""

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main([])
        self.assertEqual(exit_code, 0)
        self.assertIn("快照与离线 HTML 比对工具", output.getvalue())
        self.assertIn("选项", output.getvalue())
        self.assertNotIn("options:", output.getvalue())
        self.assertNotIn("show this help message", output.getvalue())

    def test_init_and_check_database(self) -> None:
        """CLI 应能创建数据库并执行完整性检查。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "archive.sqlite3"
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["init-db", str(path)]), 0)
                self.assertEqual(main(["check-db", str(path)]), 0)
            self.assertEqual(main(["check-project", str(path)]), 0)
            self.assertTrue(path.exists())
            self.assertIn("数据库完整性检查：ok", output.getvalue())

    def test_cli_scan_export_compare_verify_and_import(self) -> None:
        """CLI 应在不启动 GUI 时完成扫描、报告、比较、复验和导入。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            left = root / "left"
            right = root / "right"
            left.mkdir()
            right.mkdir()
            (left / "same.txt").write_text("相同", encoding="utf-8")
            (right / "same.txt").write_text("相同", encoding="utf-8")
            (right / "added.txt").write_text("新增", encoding="utf-8")
            database = root / "archive.sqlite3"
            scan_id = self._run(["scan", str(database), str(left)]).split("：", 1)[1]
            status = json.loads(self._run(["status", str(database), scan_id]))
            self.assertEqual(status[0]["status"], "COMPLETED")
            self.assertEqual(
                self._run(["export", str(database), scan_id, str(root / "scan-report")]),
                "报告已导出：" + str(root / "scan-report"),
            )
            compare_id = self._run(["compare", str(database), str(left), str(right)]).split(
                "：", 1
            )[1]
            self.assertIn("复验已完成", self._run(["verify", str(database), scan_id, str(left)]))
            self.assertIn(
                "报告已导出",
                self._run(
                    ["export", str(database), compare_id, str(root / "compare-report"), "--compare"]
                ),
            )
            imported = root / "imported.sqlite3"
            self.assertIn("项目数据库已导入", self._run(["import", str(imported), str(database)]))
            self.assertIn("检查：ok", self._run(["check-db", str(imported)]))

    def test_cli_backup_and_compare_html(self) -> None:
        """CLI 默认快照流程应直接生成可视化 HTML，并可比较两个快照。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            old_source = root / "old"
            new_source = root / "new"
            old_source.mkdir()
            new_source.mkdir()
            (old_source / "same.txt").write_text("相同", encoding="utf-8")
            (new_source / "same.txt").write_text("相同", encoding="utf-8")
            (new_source / "added.txt").write_text("新增", encoding="utf-8")
            old_archive = root / "old.html"
            new_archive = root / "new.html"
            comparison = root / "comparison.html"
            source_comparison = root / "source-comparison.html"

            self.assertIn(
                "HTML 快照已生成", self._run(["snapshot", str(old_source), str(old_archive)])
            )
            self.assertIn(
                "HTML 快照已生成", self._run(["snapshot", str(new_source), str(new_archive)])
            )
            self.assertIn(
                "HTML 目录比较报告已生成",
                self._run(
                    [
                        "compare-source",
                        str(old_archive),
                        ".",
                        str(new_source),
                        str(source_comparison),
                    ]
                ),
            )
            self.assertIn(
                "HTML 比较报告已生成",
                self._run(["compare-html", str(old_archive), str(new_archive), str(comparison)]),
            )

            self.assertTrue(old_archive.is_file())
            self.assertTrue(new_archive.is_file())
            self.assertTrue(source_comparison.is_file())
            self.assertTrue(comparison.is_file())
            self.assertIn('id="same-heading"', source_comparison.read_text(encoding="utf-8"))
            self.assertIn('id="same-heading"', comparison.read_text(encoding="utf-8"))

    def test_snapshot_cli_accepts_sampled_strategy(self) -> None:
        """快照命令应把固定预算采样策略写入 HTML。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "large.bin").write_bytes(bytes(range(64)))
            archive = root / "sampled.html"

            self._run(
                [
                    "snapshot",
                    str(source),
                    str(archive),
                    "--hash-mode",
                    "sampled",
                    "--sample-budget",
                    "8",
                    "--sample-count",
                    "4",
                ]
            )
            payload = read_html_snapshot(archive)

        self.assertEqual(payload["scan"]["hash_algorithm"], sampled_sha256_algorithm(8, 4))

    def _run(self, argv: list[str]) -> str:
        """运行一条 CLI 命令并返回去除末尾换行的标准输出。"""

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(argv), 0)
        return output.getvalue().strip()

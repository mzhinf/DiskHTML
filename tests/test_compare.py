"""流式扫描快照比较测试。"""

import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from diskhtml.compare import compare_scans, compare_source_to_scan, compare_sources
from diskhtml.config import ScanConfig
from diskhtml.database import Database
from diskhtml.models import ScanStatus
from diskhtml.report import export_compare
from diskhtml.scanner import Scanner


class CompareTests(TestCase):
    """验证路径归并、可信摘要分类与比较任务持久化。"""

    def test_compare_scans_classifies_all_result_types(self) -> None:
        """比较应以 SHA256 为最终依据，并审计两侧的非可信摘要。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with Database(Path(directory) / "archive.sqlite3") as database:
                left = self._completed_scan(
                    database,
                    (
                        ("same.txt", "A", 1, "OK"),
                        ("same_hash_size.txt", "B", 5, "OK"),
                        ("changed.txt", "C", 2, "OK"),
                        ("missing.txt", "D", 3, "OK"),
                        ("left_error.txt", None, 0, "ERROR"),
                        ("right_unstable.txt", "I", 1, "OK"),
                        ("case.txt", "E", 1, "OK"),
                    ),
                )
                right = self._completed_scan(
                    database,
                    (
                        ("same.txt", "A", 1, "OK"),
                        ("same_hash_size.txt", "B", 9, "OK"),
                        ("changed.txt", "F", 3, "OK"),
                        ("added.txt", "G", 4, "OK"),
                        ("left_error.txt", "H", 1, "OK"),
                        ("right_unstable.txt", None, 1, "UNSTABLE"),
                        ("CASE.TXT", "E", 1, "OK"),
                    ),
                )
                compare_id = compare_scans(database, left, right)
                entries = {
                    entry["relative_path"]: entry
                    for entry in database.iter_compare_entries(compare_id)
                }
                compare = database.get_compare(compare_id)

        self.assertEqual(compare["status"], "COMPLETED")
        self.assertEqual(
            json.loads(compare["summary_json"]),
            {"ADDED": 1, "CHANGED": 1, "ERROR": 2, "MATCH": 3, "MISSING": 1},
        )
        self.assertEqual(entries["same.txt"]["status"], "MATCH")
        self.assertEqual(entries["same_hash_size.txt"]["status"], "MATCH")
        self.assertEqual(entries["changed.txt"]["status"], "CHANGED")
        self.assertEqual(entries["missing.txt"]["status"], "MISSING")
        self.assertEqual(entries["added.txt"]["status"], "ADDED")
        self.assertEqual(entries["CASE.TXT"]["status"], "MATCH")
        self.assertEqual(entries["left_error.txt"]["status"], "ERROR")
        self.assertIn("左侧文件摘要状态为 ERROR", entries["left_error.txt"]["error_message"])
        self.assertEqual(entries["right_unstable.txt"]["status"], "ERROR")
        self.assertIn("右侧文件摘要状态为 UNSTABLE", entries["right_unstable.txt"]["error_message"])

    def test_compare_scans_rejects_non_completed_snapshot(self) -> None:
        """比较入口不得把未冻结的扫描任务当作历史快照。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with Database(Path(directory) / "archive.sqlite3") as database:
                incomplete = database.create_scan("DIRECTORY", "C:/incomplete", {})
                completed = self._completed_scan(database, ())
                with self.assertRaisesRegex(ValueError, "已完成"):
                    compare_scans(database, incomplete, completed)
                self.assertEqual(tuple(database.iter_scans()).__len__(), 2)

    def test_export_compare_generates_local_csv_and_report(self) -> None:
        """完成的比较任务应导出 CSV 和不依赖网络的离线报告。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            with Database(root / "archive.sqlite3") as database:
                left = self._completed_scan(
                    database, (("same.txt", "A", 1, "OK"), ("missing.txt", "B", 2, "OK"))
                )
                right = self._completed_scan(
                    database, (("same.txt", "A", 1, "OK"), ("added.txt", "C", 3, "OK"))
                )
                compare_id = compare_scans(database, left, right)
                destination = export_compare(database, compare_id, root / "compare-report")

            summary = json.loads((destination / "compare_summary.json").read_text(encoding="utf-8"))
            report = (destination / "compare_report.html").read_text(encoding="utf-8")
            manifest = (destination / "compare_assets" / "manifest.js").read_text(encoding="utf-8")
            app = (destination / "compare_assets" / "app.js").read_text(encoding="utf-8")
            with (destination / "compare_entries.csv").open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                entries = list(csv.DictReader(handle))

            self.assertEqual(
                summary["statistics"],
                {"ADDED": 1, "CHANGED": 0, "ERROR": 0, "MATCH": 1, "MISSING": 1},
            )
            self.assertEqual({entry["status"] for entry in entries}, {"ADDED", "MATCH", "MISSING"})
            self.assertIn("compare_assets/manifest.js", report)
            self.assertNotIn("http://", report + manifest)
            self.assertNotIn("fetch(", app)
            self.assertEqual(len(list((destination / "compare_assets" / "shards").glob("*.js"))), 3)
            self.assertFalse(any(root.glob(".compare-report.tmp-*")))

    def test_compare_sources_scans_two_current_directories(self) -> None:
        """两个实时目录应先各自扫描，再按左旧右新的方向比较。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            left = root / "left"
            right = root / "right"
            left.mkdir()
            right.mkdir()
            (left / "same.txt").write_text("相同", encoding="utf-8")
            (right / "same.txt").write_text("相同", encoding="utf-8")
            (left / "changed.txt").write_text("旧内容", encoding="utf-8")
            (right / "changed.txt").write_text("新内容", encoding="utf-8")
            (left / "missing.txt").write_text("仅左侧", encoding="utf-8")
            (right / "added.txt").write_text("仅右侧", encoding="utf-8")
            with Database(root / "archive.sqlite3") as database:
                compare_id = compare_sources(
                    database, str(left), str(right), ScanConfig(workers=1, queue_size=1)
                )
                statuses = {
                    entry["relative_path"]: entry["status"]
                    for entry in database.iter_compare_entries(compare_id)
                }

        self.assertEqual(
            statuses,
            {
                "added.txt": "ADDED",
                "changed.txt": "CHANGED",
                "missing.txt": "MISSING",
                "same.txt": "MATCH",
            },
        )

    def test_compare_source_to_scan_compares_current_path_with_history(self) -> None:
        """当前路径与历史快照组合入口应保留历史为左侧、当前为右侧。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            file_path = source / "entry.txt"
            file_path.write_text("历史内容", encoding="utf-8")
            with Database(root / "archive.sqlite3") as database:
                historical = Scanner(database).start(source, ScanConfig(workers=1, queue_size=1))
                file_path.write_text("当前内容", encoding="utf-8")
                compare_id = compare_source_to_scan(
                    database, str(source), historical, ScanConfig(workers=1, queue_size=1)
                )
                entry = next(database.iter_compare_entries(compare_id))

        self.assertEqual(entry["status"], "CHANGED")

    @staticmethod
    def _completed_scan(
        database: Database, files: tuple[tuple[str, str | None, int, str], ...]
    ) -> str:
        """创建一个包含指定文件记录的已完成扫描快照。"""

        scan_id = database.create_scan("DIRECTORY", "C:/source", {})
        database.set_scan_status(scan_id, ScanStatus.SCANNING)
        with database.batch() as batch:
            for relative_path, seed, size_bytes, status in files:
                batch.record_file(
                    scan_id,
                    {
                        "relative_path": relative_path,
                        "path_key": relative_path.casefold(),
                        "name": Path(relative_path).name,
                        "extension": Path(relative_path).suffix,
                        "size_bytes": size_bytes,
                        "created_time": "2026-07-24T00:00:00Z",
                        "modified_time": "2026-07-24T00:00:00Z",
                        "mtime_ns": 0,
                        "sha256": seed * 64 if seed is not None else None,
                        "sha512": None,
                        "hash_status": status,
                        "attempt_count": 1,
                        "error_code": "READ_ERROR" if status == "ERROR" else None,
                        "error_message": "无法读取" if status == "ERROR" else None,
                        "hashed_at": "2026-07-24T00:00:00Z",
                    },
                )
            batch.update_progress(scan_id, len(files), len(files), sum(item[2] for item in files))
        database.set_scan_status(scan_id, ScanStatus.COMPLETED, completed=True)
        return scan_id

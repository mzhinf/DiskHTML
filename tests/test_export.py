"""离线报告导出与原子发布测试。"""

import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from diskhtml.database import Database
from diskhtml.models import ScanStatus
from diskhtml.report import export_scan


class ExportTests(TestCase):
    """验证 CSV、JSON、HTML、分片和原子目录发布。"""

    def test_export_generates_offline_report_and_consistent_statistics(self) -> None:
        """导出应保留特殊字符，且首屏只引用本地分片清单。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            with Database(root / "archive.sqlite3") as database:
                scan_id = self._completed_scan(database)
                destination = export_scan(database, scan_id, root / "report")

            summary = json.loads((destination / "summary.json").read_text(encoding="utf-8"))
            manifest = (destination / "report_assets" / "manifest.js").read_text(encoding="utf-8")
            app = (destination / "report_assets" / "app.js").read_text(encoding="utf-8")
            report = (destination / "report.html").read_text(encoding="utf-8")
            with (destination / "file_list.csv").open(encoding="utf-8-sig", newline="") as handle:
                files = list(csv.DictReader(handle))
            with (destination / "hash_list.csv").open(encoding="utf-8-sig", newline="") as handle:
                hashes = list(csv.DictReader(handle))

            self.assertEqual(summary["statistics"]["total_files"], 3)
            self.assertEqual(summary["statistics"]["hashed_files"], 2)
            self.assertEqual(summary["statistics"]["problem_files"], 1)
            self.assertEqual(len(files), 3)
            self.assertEqual(len(hashes), 3)
            self.assertIn('资料/引号"文件.txt', {item["relative_path"] for item in files})
            self.assertIn("report_assets/manifest.js", report)
            self.assertNotIn("http://", report + manifest)
            self.assertNotIn('资料/引号"文件.txt', report + manifest)
            self.assertNotIn("fetch(", app)
            self.assertIn('id="tree"', report)
            self.assertIn('id="filter"', report)
            self.assertIn('id="detail"', report)
            self.assertIn("buildTree", app)
            self.assertIn("资料", manifest)
            self.assertEqual(len(list((destination / "report_assets" / "shards").glob("*.js"))), 2)
            self.assertFalse(any(root.glob(".report.tmp-*")))

    def test_export_refuses_incomplete_scan_and_existing_destination(self) -> None:
        """导出不能覆盖已有目录，也不能使用未完成扫描。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            with Database(root / "archive.sqlite3") as database:
                scan_id = database.create_scan("DIRECTORY", "C:/source", {})
                with self.assertRaisesRegex(ValueError, "已完成"):
                    export_scan(database, scan_id, root / "report")
                database.set_scan_status(scan_id, ScanStatus.SCANNING)
                database.set_scan_status(scan_id, ScanStatus.COMPLETED, completed=True)
                destination = export_scan(database, scan_id, root / "report")
                with self.assertRaises(FileExistsError):
                    export_scan(database, scan_id, destination)

    @staticmethod
    def _completed_scan(database: Database) -> str:
        """创建带正常和错误文件的已完成扫描快照。"""

        scan_id = database.create_scan("DIRECTORY", "C:/source", {})
        database.set_scan_status(scan_id, ScanStatus.SCANNING)
        with database.batch() as batch:
            batch.record_volume(
                scan_id,
                {
                    "drive_letter": "C:",
                    "volume_guid": "模拟卷",
                    "volume_label": "测试卷",
                    "filesystem": "NTFS",
                    "total_bytes": 100,
                    "free_bytes": 50,
                    "disk_model": None,
                    "disk_serial": None,
                    "partition_json": "[]",
                    "capture_error": None,
                },
            )
            for relative_path, status in (
                ('资料/引号"文件.txt', "OK"),
                ("资料/子目录/正常.bin", "OK"),
                ("other/错误.bin", "ERROR"),
            ):
                batch.record_file(
                    scan_id,
                    {
                        "relative_path": relative_path,
                        "path_key": relative_path.casefold(),
                        "name": Path(relative_path).name,
                        "extension": Path(relative_path).suffix,
                        "size_bytes": 4,
                        "created_time": "2026-07-24T00:00:00Z",
                        "modified_time": "2026-07-24T00:00:00Z",
                        "mtime_ns": 0,
                        "sha256": "A" * 64 if status == "OK" else None,
                        "sha512": None,
                        "hash_status": status,
                        "attempt_count": 1,
                        "error_code": "READ_ERROR" if status == "ERROR" else None,
                        "error_message": "无法读取" if status == "ERROR" else None,
                        "hashed_at": "2026-07-24T00:00:00Z",
                    },
                )
            batch.update_progress(scan_id, 3, 3, 8)
        database.set_scan_status(scan_id, ScanStatus.COMPLETED, completed=True)
        return scan_id

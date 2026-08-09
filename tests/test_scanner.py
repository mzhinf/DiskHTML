"""扫描结果批量提交集成测试。"""

import hashlib
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from diskhtml.config import HashMode
from diskhtml.database import Database
from diskhtml.models import ScanStatus
from diskhtml.sampled_hash import FULL_SHA256_ALGORITHM, sampled_sha256_algorithm
from diskhtml.scanner import Scanner, ScanOptions


class ScannerTests(TestCase):
    """验证扫描器通过单个批量事务提交已完成文件。"""

    def test_scan_persists_completed_file_batch(self) -> None:
        """两个文件应在扫描完成后具有正确的摘要和进度。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            first = source / "a.txt"
            second = source / "b.txt"
            first.write_bytes(b"alpha")
            second.write_bytes(b"beta")

            with Database(root / "archive.sqlite3") as database:
                scan_id = Scanner(database).start(
                    source,
                    ScanOptions(workers=1, queue_size=2),
                )
                job = database.get_scan(scan_id)
                records = {row["relative_path"]: row for row in database.iter_files(scan_id)}

                self.assertEqual(job["status"], ScanStatus.COMPLETED)
                self.assertEqual(job["files_hashed"], 2)
                self.assertEqual(
                    records["a.txt"]["sha256"], hashlib.sha256(b"alpha").hexdigest().upper()
                )
                self.assertEqual(
                    records["b.txt"]["sha256"], hashlib.sha256(b"beta").hexdigest().upper()
                )
                self.assertEqual(records["a.txt"]["hash_algorithm"], FULL_SHA256_ALGORITHM)

    def test_sampled_scan_records_each_files_actual_algorithm(self) -> None:
        """采样模式下，预算内文件仍为完整 Hash，大文件保存采样算法。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "small.bin").write_bytes(b"small")
            (source / "large.bin").write_bytes(bytes(range(64)))
            options = ScanOptions(
                workers=1,
                queue_size=1,
                hash_mode=HashMode.SAMPLED,
                sample_budget=8,
                sample_count=4,
            )
            with Database(root / "archive.sqlite3") as database:
                scan_id = Scanner(database).start(source, options)
                scan = database.get_scan(scan_id)
                records = {row["relative_path"]: row for row in database.iter_files(scan_id)}

        self.assertEqual(scan["hash_algorithm"], sampled_sha256_algorithm(8, 4))
        self.assertEqual(records["small.bin"]["hash_algorithm"], FULL_SHA256_ALGORITHM)
        self.assertEqual(records["large.bin"]["hash_algorithm"], sampled_sha256_algorithm(8, 4))

    def test_follow_links_handles_windows_junction_root(self) -> None:
        """启用跟随链接时，根路径为 Windows junction 也应能扫描。"""

        if os.name != "nt":
            self.skipTest("仅 Windows 支持 junction 测试")
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            target = root / "target"
            junction = root / "junction"
            target.mkdir()
            (target / "linked.txt").write_text("linked", encoding="utf-8")
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
                check=True,
                capture_output=True,
                text=True,
            )
            with Database(root / "follow.sqlite3") as database:
                scan_id = Scanner(database).start(
                    junction, ScanOptions(workers=1, queue_size=1, follow_links=True)
                )
                self.assertEqual(
                    [row["relative_path"] for row in database.iter_files(scan_id)], ["linked.txt"]
                )
            with Database(root / "default.sqlite3") as database:
                with self.assertRaises(ValueError):
                    Scanner(database).start(junction, ScanOptions(workers=1, queue_size=1))

"""扫描结果批量提交集成测试。"""

import hashlib
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from diskhtml.database import Database
from diskhtml.models import ScanStatus
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

    def test_follow_links_handles_windows_junction_root(self) -> None:
        """\u542f\u7528\u8ddf\u968f\u94fe\u63a5\u65f6\uff0c\u6839\u8def\u5f84\u4e3a Windows junction \u4e5f\u5e94\u80fd\u626b\u63cf\u3002"""

        if os.name != "nt":
            self.skipTest("\u4ec5 Windows \u652f\u6301 junction \u6d4b\u8bd5")
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

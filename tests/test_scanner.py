"""扫描结果批量提交集成测试。"""

import hashlib
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

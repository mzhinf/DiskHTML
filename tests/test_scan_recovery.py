"""扫描、Hash、暂停与恢复集成测试。"""

import hashlib
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest import TestCase
from unittest.mock import patch

from diskhtml import scanner as scanner_module
from diskhtml.database import Database
from diskhtml.models import HashStatus, ScanStatus
from diskhtml.scanner import ScanController, Scanner, ScanOptions


class ScannerTests(TestCase):
    """验证阶段 3 的扫描可靠性约束。"""

    def test_scan_persists_hashes_optional_sha512_and_progress_rate(self) -> None:
        """扫描应始终保存 SHA256，并按配置附加 SHA512 与速率。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            target = source / "a.txt"
            target.write_bytes(b"alpha")
            progress = []
            with Database(root / "archive.sqlite3") as database:
                scan_id = Scanner(database, progress.append).start(
                    source,
                    ScanOptions(workers=1, queue_size=1, sha512=True),
                )
                record = next(database.iter_files(scan_id))

            self.assertEqual(record["sha256"], hashlib.sha256(b"alpha").hexdigest().upper())
            self.assertEqual(record["sha512"], hashlib.sha512(b"alpha").hexdigest().upper())
            self.assertGreater(progress[-1].bytes_per_second, 0)
            self.assertEqual(progress[-1].estimated_remaining_seconds, 0.0)

    def test_windows_long_path_conversion_uses_extended_prefix(self) -> None:
        """Windows 长路径应转换为扩展路径前缀，不影响网络路径。"""

        with patch.object(scanner_module.os, "name", "nt"):
            self.assertEqual(
                scanner_module._filesystem_path(Path("C:/long/path")),
                "\\\\?\\C:\\long\\path",
            )
            self.assertEqual(
                scanner_module._filesystem_path(Path("//server/share/path")),
                "\\\\?\\UNC\\server\\share\\path",
            )

    def test_exclusions_apply_to_directories_and_extensions(self) -> None:
        """排除目录和扩展名不得出现在文件索引。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            (source / "ignored").mkdir(parents=True)
            (source / "keep.txt").write_text("ok", encoding="utf-8")
            (source / "drop.tmp").write_text("tmp", encoding="utf-8")
            (source / "ignored" / "hidden.txt").write_text("hidden", encoding="utf-8")
            with Database(root / "archive.sqlite3") as database:
                scan_id = Scanner(database).start(
                    source,
                    ScanOptions(exclude_dirs=("ignored",), exclude_extensions=("tmp",)),
                )
                paths = {row["relative_path"] for row in database.iter_files(scan_id)}

            self.assertEqual(paths, {"keep.txt"})

    def test_pause_persists_state_then_resume_completes_scan(self) -> None:
        """暂停必须在文件边界写入 PAUSED，继续后完成同一任务。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = self._create_source(root, 2)
            controller = ScanController()
            scanner = _BlockingScanner
            with Database(root / "archive.sqlite3") as database:
                worker = scanner(database)
                thread = Thread(
                    target=worker.start,
                    args=(source, ScanOptions(workers=1, queue_size=1), controller),
                )
                thread.start()
                self.assertTrue(worker.started.wait(2))
                controller.pause()
                worker.release.set()
                self._wait_for_status(database, ScanStatus.PAUSED)
                controller.resume()
                thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertEqual(database.latest_scan()["status"], ScanStatus.COMPLETED)

    def test_cancelled_scan_preserves_completed_file_and_resume_finishes(self) -> None:
        """取消后已完成结果应可复用，恢复后没有遗漏记录。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = self._create_source(root, 3)
            controller = ScanController()
            with Database(root / "archive.sqlite3") as database:
                scanner = _BlockingScanner(database)
                thread = Thread(
                    target=scanner.start,
                    args=(source, ScanOptions(workers=1, queue_size=1), controller),
                )
                thread.start()
                self.assertTrue(scanner.started.wait(2))
                controller.cancel()
                scanner.release.set()
                thread.join(5)
                self.assertFalse(thread.is_alive())
                scan_id = next(database.iter_scans())["id"]
                self.assertEqual(database.get_scan(scan_id)["status"], ScanStatus.CANCELLED)
                self.assertEqual(sum(1 for _ in database.iter_files(scan_id)), 1)

                Scanner(database).resume(scan_id)
                self.assertEqual(database.get_scan(scan_id)["status"], ScanStatus.COMPLETED)
                self.assertEqual(sum(1 for _ in database.iter_files(scan_id)), 3)

    def test_changed_file_is_recorded_as_unstable_without_hash(self) -> None:
        """读取期间发生变化的文件不能输出可信 SHA256。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            target = source / "changing.bin"
            target.write_bytes(b"a" * 1024)
            original_stat = scanner_module.os.stat
            target_stat_calls = 0

            def changing_stat(path: object, *args: object, **kwargs: object) -> object:
                nonlocal target_stat_calls
                if str(path).endswith("changing.bin"):
                    target_stat_calls += 1
                    if target_stat_calls == 3:
                        with target.open("ab") as handle:
                            handle.write(b"changed")
                return original_stat(path, *args, **kwargs)

            with Database(root / "archive.sqlite3") as database:
                with patch.object(scanner_module.os, "stat", changing_stat):
                    scan_id = Scanner(database).start(
                        source,
                        ScanOptions(workers=1, queue_size=1, chunk_size=64, retry_count=0),
                    )
                record = next(database.iter_files(scan_id))
                errors = tuple(database.iter_errors(scan_id))

            self.assertEqual(record["hash_status"], HashStatus.UNSTABLE)
            self.assertIsNone(record["sha256"])
            self.assertTrue(any(error["error_code"] == "CHANGED_DURING_HASH" for error in errors))

    def test_failed_task_resumes_from_committed_file_boundary(self) -> None:
        """失败任务恢复时复用已提交文件，并重新计算其余文件。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = self._create_source(root, 2)
            with Database(root / "archive.sqlite3") as database:
                options = ScanOptions(workers=1, queue_size=1)
                scan_id = database.create_scan("DIRECTORY", str(source), options.__dict__)
                database.set_scan_status(scan_id, ScanStatus.SCANNING)
                first = source / "0.txt"
                result = Scanner(database)._hash_file(first, source, options)
                with database.batch() as batch:
                    batch.record_file(scan_id, result)
                    batch.update_progress(scan_id, 1, 1, int(result["size_bytes"] or 0))
                database.set_scan_status(scan_id, ScanStatus.FAILED)

                Scanner(database).resume(scan_id)
                records = tuple(database.iter_files(scan_id))
                status = database.get_scan(scan_id)["status"]

            self.assertEqual(status, ScanStatus.COMPLETED)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["hash_status"], HashStatus.OK)

    def test_single_file_source_is_scanned_as_one_file(self) -> None:
        """单文件目标应保存 FILE 类型任务及保真相对路径。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "single.txt"
            source.write_text("single", encoding="utf-8")
            with Database(root / "archive.sqlite3") as database:
                scan_id = Scanner(database).start(source, ScanOptions(workers=1, queue_size=1))
                scan = database.get_scan(scan_id)
                record = next(database.iter_files(scan_id))

            self.assertEqual(scan["source_type"], "FILE")
            self.assertEqual(record["relative_path"], "single.txt")

    def test_missing_source_is_failed_and_audited(self) -> None:
        """不存在的源路径必须留下失败任务和错误记录。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            missing = root / "missing"
            with Database(root / "archive.sqlite3") as database:
                with self.assertRaises(FileNotFoundError):
                    Scanner(database).start(missing, ScanOptions())
                scan = next(database.iter_scans())
                errors = tuple(database.iter_errors(scan["id"]))

            self.assertEqual(scan["status"], ScanStatus.FAILED)
            self.assertEqual(errors[0]["error_code"], "SOURCE_NOT_FOUND")

    @staticmethod
    def _create_source(root: Path, count: int) -> Path:
        """创建用于暂停和取消的固定小型源目录。"""

        source = root / "source"
        source.mkdir()
        for number in range(count):
            (source / f"{number}.txt").write_text(str(number), encoding="utf-8")
        return source

    @staticmethod
    def _wait_for_status(database: Database, status: ScanStatus) -> None:
        """在有限时间内等待任务进入目标状态。"""

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            scan = next(database.iter_scans())
            if scan["status"] == status:
                return
            time.sleep(0.01)
        raise AssertionError(f"任务未进入状态：{status}")


class _BlockingScanner(Scanner):
    """在首个 Hash 开始处阻塞，便于确定性测试暂停和取消。"""

    def __init__(self, database: Database):
        super().__init__(database)
        self.started = Event()
        self.release = Event()
        self._blocked_once = False

    def _hash_file(self, path: Path, root: Path, options: ScanOptions) -> dict[str, object]:
        if not self._blocked_once:
            self._blocked_once = True
            self.started.set()
            self.release.wait(2)
        return super()._hash_file(path, root, options)

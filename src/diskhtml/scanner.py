"""有界并发文件扫描、Hash 计算、暂停与恢复实现。"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict
from fnmatch import fnmatch
from pathlib import Path
from threading import Event

from .config import ScanConfig
from .database import Database
from .disk import collect_volume_info
from .models import HashStatus, ProgressCallback, ScanProgress, ScanStatus
from .util import normalized_path_key, relative_display_path, timestamp_to_utc, utc_now

# 保留早期公开名称，后续调用方可以平滑迁移到 ScanConfig。
ScanOptions = ScanConfig


class ScanController:
    """供 GUI 或嵌入式调用方控制扫描的线程安全状态。"""

    def __init__(self) -> None:
        self._paused = Event()
        self._cancelled = Event()

    def pause(self) -> None:
        """请求暂停，工作循环会在文件边界等待。"""

        self._paused.set()

    def resume(self) -> None:
        """解除暂停请求。"""

        self._paused.clear()

    def cancel(self) -> None:
        """请求取消，已完成的文件结果仍保留用于恢复。"""

        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        """返回是否已请求取消。"""

        return self._cancelled.is_set()

    @property
    def paused(self) -> bool:
        """返回是否处于暂停状态。"""

        return self._paused.is_set()

    def wait_if_paused(self) -> None:
        """在暂停期间短暂等待，避免忙等。"""

        while self._paused.is_set() and not self._cancelled.wait(0.1):
            pass


class Scanner:
    """由一个写入线程和多个只读 Hash 工作者组成的扫描器。"""

    def __init__(self, database: Database, progress_callback: ProgressCallback | None = None):
        self.database = database
        self.progress_callback = progress_callback

    def start(
        self, source: Path | str, options: ScanOptions, controller: ScanController | None = None
    ) -> str:
        """创建并运行一个新扫描任务。"""

        path = Path(source).expanduser().resolve(strict=False)
        source_type = "FILE" if path.is_file() else "DIRECTORY"
        scan_id = self.database.create_scan(source_type, str(path), asdict(options))
        self._run(scan_id, path, options, controller or ScanController())
        return scan_id

    def resume(self, scan_id: str, controller: ScanController | None = None) -> None:
        """从已提交的稳定文件结果继续扫描。"""

        job = self.database.get_scan(scan_id)
        if job is None:
            raise ValueError(f"未找到扫描任务：{scan_id}")
        if job["status"] == ScanStatus.COMPLETED:
            raise ValueError("已完成的扫描任务无需恢复")
        import json

        options = ScanOptions(**json.loads(job["options_json"]))
        self._run(scan_id, Path(job["source_path"]), options, controller or ScanController())

    def _run(
        self, scan_id: str, source: Path, options: ScanOptions, controller: ScanController
    ) -> None:
        """执行扫描主循环；当前线程是唯一的 SQLite 写入者。"""

        if not source.exists():
            self.database.set_scan_status(scan_id, ScanStatus.FAILED)
            raise FileNotFoundError(f"扫描目标不存在：{source}")
        self.database.set_scan_status(scan_id, ScanStatus.SCANNING)
        self.database.record_volume(scan_id, collect_volume_info(source))
        root = source.parent if source.is_file() else source
        root_key = ""
        self.database.record_directory(scan_id, "", root_key, None)
        seen = 0
        completed = 0
        bytes_hashed = 0
        pending: set[Future[dict[str, object]]] = set()
        try:
            with ThreadPoolExecutor(
                max_workers=max(1, options.workers), thread_name_prefix="hash"
            ) as executor:
                for path in self._iter_paths(source, root, options, scan_id):
                    controller.wait_if_paused()
                    if controller.cancelled:
                        break
                    seen += 1
                    relative_path = relative_display_path(path, root)
                    path_key = normalized_path_key(relative_path)
                    stat = path.stat(follow_symlinks=False)
                    existing = self.database.get_file(scan_id, path_key)
                    if self._is_reusable(existing, stat):
                        completed += 1
                        bytes_hashed += stat.st_size
                        self._notify(scan_id, seen, completed, bytes_hashed, relative_path)
                        continue
                    pending.add(executor.submit(self._hash_file, path, root, options))
                    if len(pending) >= max(1, options.queue_size):
                        done, pending = wait(pending, return_when=FIRST_COMPLETED)
                        completed, bytes_hashed = self._store_done(
                            scan_id, done, seen, completed, bytes_hashed
                        )
                while pending:
                    controller.wait_if_paused()
                    if controller.cancelled:
                        for future in pending:
                            future.cancel()
                        break
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    completed, bytes_hashed = self._store_done(
                        scan_id, done, seen, completed, bytes_hashed
                    )
            self.database.update_progress(scan_id, seen, completed, bytes_hashed)
            if controller.cancelled:
                self.database.set_scan_status(scan_id, ScanStatus.CANCELLED)
            else:
                self.database.set_scan_status(scan_id, ScanStatus.COMPLETED, completed=True)
        except Exception:
            self.database.set_scan_status(scan_id, ScanStatus.FAILED)
            raise

    def _store_done(
        self,
        scan_id: str,
        done: set[Future[dict[str, object]]],
        seen: int,
        completed: int,
        bytes_hashed: int,
    ) -> tuple[int, int]:
        """由唯一写入线程提交完成的 Hash 结果。"""

        for future in done:
            result = future.result()
            self.database.record_file(scan_id, result)
            completed += 1
            if result["hash_status"] == HashStatus.OK:
                bytes_hashed += int(result["size_bytes"] or 0)
            self.database.update_progress(scan_id, seen, completed, bytes_hashed)
            self._notify(scan_id, seen, completed, bytes_hashed, str(result["relative_path"]))
        return completed, bytes_hashed

    def _iter_paths(
        self, source: Path, root: Path, options: ScanOptions, scan_id: str
    ) -> Iterator[Path]:
        """递归枚举普通文件，跳过链接和重解析点。"""

        if source.is_file():
            yield source
            return
        stack = [source]
        while stack:
            directory = stack.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        path = Path(entry.path)
                        try:
                            if entry.is_symlink():
                                continue
                            relative = relative_display_path(path, root)
                            if entry.is_dir(follow_symlinks=False):
                                if self._excluded_directory(relative, options):
                                    continue
                                key = normalized_path_key(relative)
                                parent_key = (
                                    normalized_path_key(Path(relative).parent.as_posix())
                                    if Path(relative).parent.as_posix() != "."
                                    else ""
                                )
                                self.database.record_directory(scan_id, relative, key, parent_key)
                                stack.append(path)
                            elif entry.is_file(follow_symlinks=False) and not self._excluded_file(
                                path, options
                            ):
                                yield path
                        except OSError as exc:
                            self.database.record_error(
                                scan_id,
                                relative if "relative" in locals() else None,
                                "ENTRY_ERROR",
                                str(exc),
                            )
            except OSError as exc:
                relative = relative_display_path(directory, root) if directory != root else ""
                self.database.record_directory(
                    scan_id, relative, normalized_path_key(relative), None, str(exc)
                )
                self.database.record_error(scan_id, relative, "DIRECTORY_ERROR", str(exc))

    @staticmethod
    def _excluded_directory(relative_path: str, options: ScanOptions) -> bool:
        """根据目录模式判断是否排除。"""

        return any(
            fnmatch(relative_path, pattern) or pattern in Path(relative_path).parts
            for pattern in options.exclude_dirs
        )

    @staticmethod
    def _excluded_file(path: Path, options: ScanOptions) -> bool:
        """根据扩展名判断是否排除。"""

        suffix = path.suffix.casefold()
        return suffix in {
            item.casefold() if item.startswith(".") else f".{item.casefold()}"
            for item in options.exclude_extensions
        }

    @staticmethod
    def _is_reusable(existing: object, stat: os.stat_result) -> bool:
        """只有元数据未变化且上次 Hash 成功的文件才可在恢复时复用。"""

        return bool(
            existing
            and existing["hash_status"] == HashStatus.OK
            and existing["size_bytes"] == stat.st_size
            and existing["mtime_ns"] == stat.st_mtime_ns
        )

    def _hash_file(self, path: Path, root: Path, options: ScanOptions) -> dict[str, object]:
        """分块读取文件，检测读取过程中发生的变化并有限重试。"""

        relative_path = relative_display_path(path, root)
        path_key = normalized_path_key(relative_path)
        extension = path.suffix.casefold()
        last_result: dict[str, object] | None = None
        for attempt in range(1, options.retry_count + 2):
            try:
                before = path.stat(follow_symlinks=False)
                sha256 = hashlib.sha256()
                sha512 = hashlib.sha512() if options.sha512 else None
                with path.open("rb", buffering=0) as handle:
                    while block := handle.read(options.chunk_size):
                        sha256.update(block)
                        if sha512 is not None:
                            sha512.update(block)
                after = path.stat(follow_symlinks=False)
                base = self._base_file_result(
                    relative_path, path_key, path.name, extension, before, attempt
                )
                if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
                    last_result = {
                        **base,
                        "hash_status": HashStatus.UNSTABLE,
                        "error_code": "CHANGED_DURING_HASH",
                        "error_message": "文件在 Hash 计算期间发生变化。",
                    }
                    continue
                return {
                    **base,
                    "sha256": sha256.hexdigest().upper(),
                    "sha512": sha512.hexdigest().upper() if sha512 else None,
                    "hash_status": HashStatus.OK,
                    "error_code": None,
                    "error_message": None,
                    "hashed_at": utc_now(),
                }
            except OSError as exc:
                try:
                    stat = path.stat(follow_symlinks=False)
                    base = self._base_file_result(
                        relative_path, path_key, path.name, extension, stat, attempt
                    )
                except OSError:
                    base = {
                        "relative_path": relative_path,
                        "path_key": path_key,
                        "name": path.name,
                        "extension": extension,
                        "size_bytes": None,
                        "created_time": None,
                        "modified_time": None,
                        "mtime_ns": None,
                        "attempt_count": attempt,
                    }
                return {
                    **base,
                    "sha256": None,
                    "sha512": None,
                    "hash_status": HashStatus.ERROR,
                    "error_code": type(exc).__name__,
                    "error_message": str(exc),
                    "hashed_at": utc_now(),
                }
        assert last_result is not None
        return {**last_result, "sha256": None, "sha512": None, "hashed_at": utc_now()}

    @staticmethod
    def _base_file_result(
        relative_path: str,
        path_key: str,
        name: str,
        extension: str,
        stat: os.stat_result,
        attempt: int,
    ) -> dict[str, object]:
        """构造所有结果状态共享的文件元数据。"""

        return {
            "relative_path": relative_path,
            "path_key": path_key,
            "name": name,
            "extension": extension,
            "size_bytes": stat.st_size,
            "created_time": timestamp_to_utc(stat.st_ctime_ns),
            "modified_time": timestamp_to_utc(stat.st_mtime_ns),
            "mtime_ns": stat.st_mtime_ns,
            "attempt_count": attempt,
        }

    def _notify(
        self, scan_id: str, seen: int, completed: int, bytes_hashed: int, current_path: str | None
    ) -> None:
        """在存在回调时发送进度快照。"""

        if self.progress_callback:
            self.progress_callback(
                ScanProgress(scan_id, seen, completed, bytes_hashed, current_path)
            )

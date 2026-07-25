"""有界并发文件扫描、Hash 计算、暂停与恢复实现。"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict
from fnmatch import fnmatch
from pathlib import Path
from threading import Event
from time import monotonic

from .config import ScanConfig
from .database import Database
from .disk import collect_volume_info
from .models import ErrorCode, HashStatus, ProgressCallback, ScanProgress, ScanStatus
from .util import normalized_path_key, relative_display_path, timestamp_to_utc, utc_now

# 保留早期公开名称，后续调用方可以平滑迁移到 ScanConfig。
ScanOptions = ScanConfig
_REPARSE_POINT_ATTRIBUTE = 0x400


def _filesystem_path(path: Path) -> str:
    """返回可供 Windows 长路径 API 使用的本地路径。"""

    text = str(path.absolute())
    if os.name != "nt" or text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


class ScanController:
    """供 GUI 或嵌入式调用方控制扫描的线程安全状态。"""

    def __init__(self) -> None:
        self._paused = Event()
        self._cancelled = Event()

    def pause(self) -> None:
        """请求暂停；扫描器会在下一个文件边界持久化 PAUSED。"""

        self._paused.set()

    def resume(self) -> None:
        """解除暂停请求。"""

        self._paused.clear()

    def cancel(self) -> None:
        """请求取消；已完整提交的文件结果保留给后续恢复。"""

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

        requested_path = Path(source).expanduser()
        source_is_link = self._is_reparse_path(requested_path)
        path = (
            requested_path.absolute()
            if source_is_link and options.follow_links
            else requested_path.resolve(strict=False)
        )
        source_type = (
            "FILE"
            if path.is_file()
            else "VOLUME"
            if path.anchor and path == Path(path.anchor)
            else "DIRECTORY"
        )
        scan_id = self.database.create_scan(source_type, str(path), asdict(options))
        if source_is_link and not options.follow_links:
            self.database.record_error(
                scan_id,
                None,
                "REPARSE_POINT",
                "默认不跟随符号链接或 Windows 重解析点。",
            )
            self.database.set_scan_status(scan_id, ScanStatus.FAILED)
            raise ValueError("扫描目标不能是符号链接或重解析点")
        self._run(scan_id, path, options, controller or ScanController())
        return scan_id

    def resume(self, scan_id: str, controller: ScanController | None = None) -> None:
        """从已提交的稳定文件结果继续扫描。"""

        job = self.database.get_scan(scan_id)
        if job is None:
            raise ValueError(f"未找到扫描任务：{scan_id}")
        if job["status"] == ScanStatus.COMPLETED:
            raise ValueError("已完成的扫描任务无需恢复")
        options = ScanOptions(**json.loads(job["options_json"]))
        self._run(scan_id, Path(job["source_path"]), options, controller or ScanController())

    def _run(
        self, scan_id: str, source: Path, options: ScanOptions, controller: ScanController
    ) -> None:
        """执行扫描主循环；当前线程是唯一的 SQLite 写入者。"""

        started = monotonic()
        if not source.exists():
            self.database.record_error(
                scan_id, None, "SOURCE_NOT_FOUND", f"扫描目标不存在：{source}"
            )
            self.database.set_scan_status(scan_id, ScanStatus.FAILED)
            raise FileNotFoundError(f"扫描目标不存在：{source}")
        if source.is_symlink() and not options.follow_links:
            self.database.record_error(
                scan_id, None, "REPARSE_POINT", "默认不跟随符号链接或 Windows 重解析点。"
            )
            self.database.set_scan_status(scan_id, ScanStatus.FAILED)
            raise ValueError("扫描目标不能是符号链接或重解析点")

        self.database.set_scan_status(scan_id, ScanStatus.SCANNING)
        self.database.record_volume(scan_id, collect_volume_info(source))
        root = source.parent if source.is_file() else source
        try:
            root_stat = os.stat(_filesystem_path(root), follow_symlinks=options.follow_links)
        except OSError:
            root_stat = None
        self.database.record_directory(
            scan_id,
            "",
            "",
            None,
            created_time=timestamp_to_utc(root_stat.st_ctime_ns) if root_stat else None,
            modified_time=timestamp_to_utc(root_stat.st_mtime_ns) if root_stat else None,
        )
        seen = 0
        completed = 0
        bytes_hashed = 0
        known_bytes = 0
        pending: set[Future[dict[str, object]]] = set()
        cancelled = False
        try:
            with ThreadPoolExecutor(
                max_workers=max(1, options.workers), thread_name_prefix="hash"
            ) as executor:
                for path in self._iter_paths(source, root, options, scan_id):
                    self._wait_at_file_boundary(scan_id, controller)
                    if controller.cancelled:
                        cancelled = True
                        break
                    seen += 1
                    relative_path = relative_display_path(path, root)
                    path_key = normalized_path_key(relative_path)
                    try:
                        stat = os.stat(_filesystem_path(path), follow_symlinks=options.follow_links)
                    except OSError:
                        stat = None
                    if stat is not None:
                        known_bytes += stat.st_size
                    existing = self.database.get_file(scan_id, path_key)
                    if stat is not None and self._is_reusable(existing, stat):
                        completed += 1
                        bytes_hashed += stat.st_size
                        self._notify(
                            scan_id,
                            seen,
                            completed,
                            bytes_hashed,
                            known_bytes,
                            relative_path,
                            started,
                        )
                        continue
                    pending.add(executor.submit(self._hash_file, path, root, options))
                    if len(pending) >= max(1, options.queue_size):
                        done, pending = wait(pending, return_when=FIRST_COMPLETED)
                        completed, bytes_hashed = self._store_done(
                            scan_id, done, seen, completed, bytes_hashed, known_bytes, started
                        )

                while pending and not cancelled:
                    self._wait_at_file_boundary(scan_id, controller)
                    if controller.cancelled:
                        cancelled = True
                        break
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    completed, bytes_hashed = self._store_done(
                        scan_id, done, seen, completed, bytes_hashed, known_bytes, started
                    )

                if cancelled:
                    for future in pending:
                        future.cancel()

            if cancelled:
                finished = {future for future in pending if not future.cancelled()}
                if finished:
                    completed, bytes_hashed = self._store_done(
                        scan_id, finished, seen, completed, bytes_hashed, known_bytes, started
                    )
            self.database.update_progress(scan_id, seen, completed, bytes_hashed)
            if cancelled:
                self.database.set_scan_status(scan_id, ScanStatus.CANCELLED)
            else:
                self.database.set_scan_status(scan_id, ScanStatus.COMPLETED, completed=True)
        except Exception:
            job = self.database.get_scan(scan_id)
            if job is not None and job["status"] != ScanStatus.COMPLETED:
                self.database.set_scan_status(scan_id, ScanStatus.FAILED)
            raise

    def _wait_at_file_boundary(self, scan_id: str, controller: ScanController) -> None:
        """持久化暂停状态，并在继续后恢复 SCANNING。"""

        if not controller.paused:
            return
        job = self.database.get_scan(scan_id)
        if job is not None and job["status"] == ScanStatus.SCANNING:
            self.database.set_scan_status(scan_id, ScanStatus.PAUSED)
        controller.wait_if_paused()
        if controller.cancelled:
            return
        job = self.database.get_scan(scan_id)
        if job is not None and job["status"] == ScanStatus.PAUSED:
            self.database.set_scan_status(scan_id, ScanStatus.SCANNING)

    def _store_done(
        self,
        scan_id: str,
        done: set[Future[dict[str, object]]],
        seen: int,
        completed: int,
        bytes_hashed: int,
        known_bytes: int,
        started: float,
    ) -> tuple[int, int]:
        """由唯一写入线程提交完成的 Hash 结果。"""

        results = [future.result() for future in done if not future.cancelled()]
        for result in results:
            completed += 1
            if result["hash_status"] == HashStatus.OK:
                bytes_hashed += int(result["size_bytes"] or 0)

        if results:
            with self.database.batch() as batch:
                for result in results:
                    batch.record_file(scan_id, result)
                    if result["hash_status"] != HashStatus.OK:
                        batch.record_error(
                            scan_id,
                            str(result["relative_path"]),
                            str(result.get("error_code") or "HASH_ERROR"),
                            str(result.get("error_message") or "文件 Hash 未完成。"),
                        )
                batch.update_progress(scan_id, seen, completed, bytes_hashed)

        for result in results:
            self._notify(
                scan_id,
                seen,
                completed,
                bytes_hashed,
                known_bytes,
                str(result["relative_path"]),
                started,
            )
        return completed, bytes_hashed

    def _iter_paths(
        self, source: Path, root: Path, options: ScanOptions, scan_id: str
    ) -> Iterator[Path]:
        """\u8bc6\u522b\u7b26\u53f7\u94fe\u63a5\u548c Windows junction\uff0c\u786e\u4fdd\u6839\u8def\u5f84\u4e0e\u5b50\u9879\u4f7f\u7528\u4e00\u81f4\u89c4\u5219\u3002"""

        if source.is_file():
            if not self._excluded_file(source, options):
                yield source
            return
        stack = [source]
        visited_targets: set[tuple[int, int]] = set()
        while stack:
            directory = stack.pop()
            if options.follow_links:
                try:
                    target_stat = os.stat(_filesystem_path(directory), follow_symlinks=True)
                    target_key = (target_stat.st_dev, target_stat.st_ino)
                except OSError as exc:
                    relative = relative_display_path(directory, root) if directory != root else ""
                    self.database.record_error(
                        scan_id, relative, self._error_code(exc, ErrorCode.ENTRY_ERROR), str(exc)
                    )
                    continue
                if target_key in visited_targets:
                    continue
                visited_targets.add(target_key)
            try:
                with os.scandir(_filesystem_path(directory)) as entries:
                    for entry in entries:
                        path = directory / entry.name
                        relative = relative_display_path(path, root)
                        try:
                            linked = entry.is_symlink() or self._is_reparse_point(entry)
                            if linked and not options.follow_links:
                                self.database.record_error(
                                    scan_id,
                                    relative,
                                    "REPARSE_POINT",
                                    "默认不跟随符号链接或 Windows 重解析点。",
                                )
                                continue
                            if entry.is_dir(follow_symlinks=options.follow_links):
                                if self._excluded_directory(relative, options):
                                    continue
                                key = normalized_path_key(relative)
                                parent = Path(relative).parent.as_posix()
                                parent_key = normalized_path_key(parent) if parent != "." else ""
                                directory_stat = entry.stat(follow_symlinks=options.follow_links)
                                self.database.record_directory(
                                    scan_id,
                                    relative,
                                    key,
                                    parent_key,
                                    created_time=timestamp_to_utc(directory_stat.st_ctime_ns),
                                    modified_time=timestamp_to_utc(directory_stat.st_mtime_ns),
                                )
                                stack.append(path)
                            elif entry.is_file(
                                follow_symlinks=options.follow_links
                            ) and not self._excluded_file(path, options):
                                yield path
                        except OSError as exc:
                            self.database.record_error(
                                scan_id,
                                relative,
                                self._error_code(exc, ErrorCode.ENTRY_ERROR),
                                str(exc),
                            )
            except OSError as exc:
                relative = relative_display_path(directory, root) if directory != root else ""
                self.database.record_directory(
                    scan_id, relative, normalized_path_key(relative), None, str(exc)
                )
                self.database.record_error(
                    scan_id, relative, self._error_code(exc, ErrorCode.ENTRY_ERROR), str(exc)
                )

    @staticmethod
    def _is_reparse_path(path: Path) -> bool:
        """\u8bc6\u522b\u7b26\u53f7\u94fe\u63a5\u548c Windows junction\uff0c\u786e\u4fdd\u6839\u8def\u5f84\u4e0e\u5b50\u9879\u4f7f\u7528\u4e00\u81f4\u89c4\u5219\u3002"""

        if path.is_symlink():
            return True
        if os.name != "nt":
            return False
        try:
            return bool(
                os.lstat(_filesystem_path(path)).st_file_attributes & _REPARSE_POINT_ATTRIBUTE
            )
        except OSError:
            return False

    @staticmethod
    def _is_reparse_point(entry: os.DirEntry[str]) -> bool:
        """识别 Windows 重解析点，避免目录联接导致循环或越界。"""

        if os.name != "nt":
            return False
        return bool(entry.stat(follow_symlinks=False).st_file_attributes & _REPARSE_POINT_ATTRIBUTE)

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
                before = os.stat(_filesystem_path(path), follow_symlinks=options.follow_links)
                sha256 = hashlib.sha256()
                sha512 = hashlib.sha512() if options.sha512 else None
                with open(_filesystem_path(path), "rb", buffering=0) as handle:
                    while block := handle.read(options.chunk_size):
                        sha256.update(block)
                        if sha512 is not None:
                            sha512.update(block)
                after = os.stat(_filesystem_path(path), follow_symlinks=options.follow_links)
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
                    stat = os.stat(_filesystem_path(path), follow_symlinks=options.follow_links)
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
                    "error_code": self._error_code(exc, ErrorCode.READ_ERROR),
                    "error_message": str(exc),
                    "hashed_at": utc_now(),
                }
        assert last_result is not None
        return {**last_result, "sha256": None, "sha512": None, "hashed_at": utc_now()}

    @staticmethod
    def _error_code(exc: OSError, fallback: ErrorCode) -> ErrorCode:
        """把系统访问异常转换为持久化的稳定领域错误码。"""

        if isinstance(exc, PermissionError):
            return ErrorCode.PERMISSION_DENIED
        if isinstance(exc, FileNotFoundError):
            return ErrorCode.FILE_DISAPPEARED
        return fallback

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
        self,
        scan_id: str,
        seen: int,
        completed: int,
        bytes_hashed: int,
        known_bytes: int,
        current_path: str | None,
        started: float,
    ) -> None:
        """在存在回调时发送包含速率的进度快照。"""

        if self.progress_callback:
            elapsed = max(monotonic() - started, 0.001)
            bytes_per_second = bytes_hashed / elapsed
            estimated_remaining = (
                max(known_bytes - bytes_hashed, 0) / bytes_per_second
                if bytes_per_second > 0
                else None
            )
            self.progress_callback(
                ScanProgress(
                    scan_id,
                    seen,
                    completed,
                    bytes_hashed,
                    current_path,
                    bytes_per_second,
                    estimated_remaining,
                )
            )

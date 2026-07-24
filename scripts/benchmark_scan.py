"""生成可复现的 DiskHTML 扫描与报告性能基准结果。"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import sys
import threading
from pathlib import Path
from time import perf_counter

from diskhtml.config import ScanConfig
from diskhtml.database import Database
from diskhtml.report import export_scan
from diskhtml.scanner import Scanner


def _working_set_bytes() -> int | None:
    """读取 Windows 当前进程工作集；调用失败时返回空值。"""

    if os.name != "nt":
        return None

    class MemoryCounters(ctypes.Structure):
        """声明 Windows 工作集 API 所需的内存计数器结构。"""

        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("page_fault_count", ctypes.c_ulong),
            ("peak_working_set", ctypes.c_size_t),
            ("working_set", ctypes.c_size_t),
            ("quota_peak_paged_pool", ctypes.c_size_t),
            ("quota_paged_pool", ctypes.c_size_t),
            ("quota_peak_non_paged_pool", ctypes.c_size_t),
            ("quota_non_paged_pool", ctypes.c_size_t),
            ("pagefile", ctypes.c_size_t),
            ("peak_pagefile", ctypes.c_size_t),
        ]

    counters = MemoryCounters(cb=ctypes.sizeof(MemoryCounters))
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(MemoryCounters),
            ctypes.c_ulong,
        )
        psapi.GetProcessMemoryInfo.restype = ctypes.c_bool
        success = psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        )
    except (AttributeError, OSError):
        return None
    return int(counters.working_set) if success else None


class WorkingSetSampler:
    """在扫描和报告导出期间采样峰值工作集。"""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self.peak_bytes: int | None = None

    def start(self) -> None:
        """启动采样线程。"""

        self._record()
        self._thread.start()

    def stop(self) -> int | None:
        """停止采样线程并返回峰值。"""

        self._stop.set()
        self._thread.join()
        self._record()
        return self.peak_bytes

    def _sample(self) -> None:
        while not self._stop.wait(0.05):
            self._record()

    def _record(self) -> None:
        value = _working_set_bytes()
        if value is not None:
            self.peak_bytes = max(self.peak_bytes or 0, value)


def _path_size(path: Path) -> int:
    """计算文件或目录大小，不读取文件内容。"""

    return (
        path.stat().st_size
        if path.is_file()
        else sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    )


def _parser() -> argparse.ArgumentParser:
    """构建基准命令参数。"""

    parser = argparse.ArgumentParser(description="DiskHTML 扫描性能基准")
    parser.add_argument("source", type=Path, help="要扫描的现有文件或目录")
    parser.add_argument("output", type=Path, help="新建的基准结果目录")
    parser.add_argument("--workers", type=int, default=2, help="Hash 工作线程数")
    parser.add_argument("--queue-size", type=int, default=32, help="有界任务队列大小")
    parser.add_argument("--chunk-size", type=int, default=4 * 1024 * 1024, help="单次读取字节数")
    parser.add_argument("--sha512", action="store_true", help="同时计算 SHA512")
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行一次扫描和报告导出，保存 JSON 结果。"""

    args = _parser().parse_args(argv)
    source, output = args.source.expanduser(), args.output.expanduser()
    if not source.exists():
        raise ValueError(f"扫描源不存在：{source}")
    if output.exists():
        raise FileExistsError(f"基准结果目录已存在：{output}")

    options = ScanConfig(
        workers=args.workers,
        queue_size=args.queue_size,
        chunk_size=args.chunk_size,
        sha512=args.sha512,
    )
    output.mkdir(parents=True)
    sampler = WorkingSetSampler()
    try:
        with Database(output / "archive.sqlite3") as database:
            sampler.start()
            try:
                started = perf_counter()
                scan_id = Scanner(database).start(source, options)
                scan_seconds = perf_counter() - started
                job = database.get_scan(scan_id)
                if job is None:
                    raise RuntimeError("扫描完成后未找到任务记录")
                summary = database.summary(scan_id)

                started = perf_counter()
                export_scan(database, scan_id, output / "report")
                report_seconds = perf_counter() - started
                database.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            finally:
                peak_working_set = sampler.stop()

        hashed_bytes = int(job["bytes_hashed"])
        result = {
            "format_version": 1,
            "platform": platform.platform(),
            "python_version": sys.version.split()[0],
            "source": str(source.resolve()),
            "options": {
                "workers": options.workers,
                "queue_size": options.queue_size,
                "chunk_size": options.chunk_size,
                "sha512": options.sha512,
            },
            "scan": {
                "seconds": round(scan_seconds, 6),
                "files_seen": int(job["files_seen"]),
                "files_hashed": int(job["files_hashed"]),
                "bytes_hashed": hashed_bytes,
                "throughput_bytes_per_second": round(hashed_bytes / scan_seconds, 2)
                if scan_seconds
                else None,
                "statistics": summary,
            },
            "report": {"seconds": round(report_seconds, 6)},
            "storage": {
                "database_bytes": _path_size(output / "archive.sqlite3"),
                "report_bytes": _path_size(output / "report"),
            },
            "memory": {"peak_working_set_bytes": peak_working_set},
        }
        result_path = output / "result.json"
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except BaseException:
        print(f"基准执行失败，已保留现场目录：{output}", file=sys.stderr)
        raise

    print(f"基准结果：{result_path}")
    print(f"Hash 吞吐：{result['scan']['throughput_bytes_per_second']} 字节/秒")
    print(f"扫描耗时：{result['scan']['seconds']} 秒；报告耗时：{result['report']['seconds']} 秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

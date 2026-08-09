"""两套命令行入口共享的扫描参数声明与配置合并。"""

from __future__ import annotations

import argparse
from dataclasses import replace

from .config import HashMode, ScanConfig


def add_scan_options(
    parser: argparse.ArgumentParser, *, include_hash_strategy: bool = True
) -> None:
    """按稳定顺序添加有界资源、链接和可选 Hash 策略参数。"""

    parser.add_argument("--workers", type=int, help="Hash 工作线程数")
    parser.add_argument("--queue-size", type=int, help="有界任务队列大小")
    parser.add_argument("--chunk-size", type=int, help="每次读取的字节数")
    parser.add_argument("--sha512", action="store_true", help="额外计算 SHA512")
    parser.add_argument("--follow-links", action="store_true", help="跟随软链接和 Windows 重解析点")
    if include_hash_strategy:
        parser.add_argument(
            "--hash-mode",
            choices=tuple(mode.value for mode in HashMode),
            help="SHA-256 计算模式：full 或 sampled",
        )
        parser.add_argument(
            "--sample-target-bytes",
            dest="sample_target_bytes",
            type=int,
            help="目标采样读取量，单位为字节",
        )
        parser.add_argument("--sample-count", type=int, help="固定采样次数，范围为 2 到 32")


def merge_scan_config(defaults: ScanConfig, args: argparse.Namespace) -> ScanConfig:
    """将命令行覆盖项合并到配置默认值，并保留未暴露的策略字段。"""

    hash_mode = getattr(args, "hash_mode", None)
    sample_target_bytes = getattr(args, "sample_target_bytes", None)
    sample_count = getattr(args, "sample_count", None)
    return replace(
        defaults,
        workers=args.workers if args.workers is not None else defaults.workers,
        queue_size=args.queue_size if args.queue_size is not None else defaults.queue_size,
        chunk_size=args.chunk_size if args.chunk_size is not None else defaults.chunk_size,
        sha512=args.sha512 or defaults.sha512,
        hash_mode=HashMode(hash_mode) if hash_mode else defaults.hash_mode,
        sample_target_bytes=(
            sample_target_bytes if sample_target_bytes is not None else defaults.sample_target_bytes
        ),
        sample_count=sample_count if sample_count is not None else defaults.sample_count,
        follow_links=args.follow_links or defaults.follow_links,
    )

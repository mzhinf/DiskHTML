"""版本化 TOML 配置的读取与校验。"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from .sampled_hash import (
    DEFAULT_SAMPLE_BUDGET,
    DEFAULT_SAMPLE_COUNT,
    FULL_SHA256_ALGORITHM,
    sampled_sha256_algorithm,
)

CONFIG_VERSION = 1
VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class HashMode(StrEnum):
    """扫描任务可请求的 SHA-256 计算模式。"""

    FULL = "full"
    SAMPLED = "sampled"


@dataclass(frozen=True)
class ScanConfig:
    """扫描配置；创建任务后应作为不可变快照保存。"""

    workers: int = 2
    queue_size: int = 32
    chunk_size: int = 4 * 1024 * 1024
    exclude_dirs: tuple[str, ...] = field(default_factory=tuple)
    exclude_extensions: tuple[str, ...] = field(default_factory=tuple)
    sha512: bool = False
    hash_mode: HashMode = HashMode.FULL
    sample_budget: int = DEFAULT_SAMPLE_BUDGET
    sample_count: int = DEFAULT_SAMPLE_COUNT
    follow_links: bool = False
    retry_count: int = 1

    def __post_init__(self) -> None:
        """拒绝会破坏有界内存或导致无效读取的配置。"""

        try:
            hash_mode = HashMode(self.hash_mode)
        except ValueError as exc:
            raise ValueError(f"不支持的 Hash 模式：{self.hash_mode}") from exc
        object.__setattr__(self, "hash_mode", hash_mode)
        sampled_sha256_algorithm(self.sample_budget, self.sample_count)
        if hash_mode is HashMode.SAMPLED and self.sha512:
            raise ValueError("采样 Hash 模式不能同时计算完整 SHA-512")
        if self.workers < 1:
            raise ValueError("扫描工作线程数必须大于等于 1")
        if self.queue_size < 1:
            raise ValueError("任务队列大小必须大于等于 1")
        if self.chunk_size < 1:
            raise ValueError("读取块大小必须大于等于 1")
        if self.retry_count < 0:
            raise ValueError("重试次数不能为负数")

    def requested_hash_algorithm(self) -> str:
        """返回扫描任务请求并写入快照的算法策略标识。"""

        if self.hash_mode is HashMode.SAMPLED:
            return sampled_sha256_algorithm(self.sample_budget, self.sample_count)
        return FULL_SHA256_ALGORITHM

    def effective_hash_algorithm(self, file_size: int) -> str:
        """根据文件大小返回该文件实际使用的算法标识。"""

        if file_size < 0:
            raise ValueError("文件大小不能为负数")
        if self.hash_mode is HashMode.SAMPLED and file_size > self.sample_budget:
            return sampled_sha256_algorithm(self.sample_budget, self.sample_count)
        return FULL_SHA256_ALGORITHM


@dataclass(frozen=True)
class AppConfig:
    """应用配置根对象。"""

    format_version: int = CONFIG_VERSION
    log_level: str = "INFO"
    json_log: bool = False
    scan: ScanConfig = field(default_factory=ScanConfig)


def load_config(path: Path | str | None) -> AppConfig:
    """读取配置文件；未指定路径时返回安全默认值。"""

    if path is None:
        return AppConfig()
    config_path = Path(path)
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return _parse_config(raw)


def _parse_config(raw: dict[str, Any]) -> AppConfig:
    """把已解析 TOML 转换为强类型配置。"""

    version = int(raw.get("format_version", CONFIG_VERSION))
    if version != CONFIG_VERSION:
        raise ValueError(f"不支持的配置格式版本：{version}")

    logging_values = raw.get("logging", {})
    if not isinstance(logging_values, dict):
        raise ValueError("配置项 logging 必须是表")
    log_level = str(logging_values.get("level", "INFO")).upper()
    if log_level not in VALID_LOG_LEVELS:
        raise ValueError(f"不支持的日志级别：{log_level}")

    scan_values = raw.get("scan", {})
    if not isinstance(scan_values, dict):
        raise ValueError("配置项 scan 必须是表")
    scan = ScanConfig(
        workers=int(scan_values.get("workers", 2)),
        queue_size=int(scan_values.get("queue_size", 32)),
        chunk_size=int(scan_values.get("chunk_size", 4 * 1024 * 1024)),
        exclude_dirs=tuple(str(item) for item in scan_values.get("exclude_dirs", [])),
        exclude_extensions=tuple(str(item) for item in scan_values.get("exclude_extensions", [])),
        sha512=bool(scan_values.get("sha512", False)),
        hash_mode=HashMode(str(scan_values.get("hash_mode", HashMode.FULL))),
        sample_budget=int(scan_values.get("sample_budget", DEFAULT_SAMPLE_BUDGET)),
        sample_count=int(scan_values.get("sample_count", DEFAULT_SAMPLE_COUNT)),
        follow_links=bool(scan_values.get("follow_links", False)),
        retry_count=int(scan_values.get("retry_count", 1)),
    )
    return AppConfig(
        format_version=version,
        log_level=log_level,
        json_log=bool(logging_values.get("json", False)),
        scan=scan,
    )

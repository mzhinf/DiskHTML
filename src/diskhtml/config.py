"""版本化 TOML 配置的读取与校验。"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_VERSION = 1
VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


@dataclass(frozen=True)
class ScanConfig:
    """扫描配置；创建任务后应作为不可变快照保存。"""

    workers: int = 2
    queue_size: int = 32
    chunk_size: int = 4 * 1024 * 1024
    exclude_dirs: tuple[str, ...] = field(default_factory=tuple)
    exclude_extensions: tuple[str, ...] = field(default_factory=tuple)
    sha512: bool = False
    follow_links: bool = False
    retry_count: int = 1

    def __post_init__(self) -> None:
        """拒绝会破坏有界内存或导致无效读取的配置。"""

        if self.workers < 1:
            raise ValueError("扫描工作线程数必须大于等于 1")
        if self.queue_size < 1:
            raise ValueError("任务队列大小必须大于等于 1")
        if self.chunk_size < 1:
            raise ValueError("读取块大小必须大于等于 1")
        if self.retry_count < 0:
            raise ValueError("重试次数不能为负数")


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
        follow_links=bool(scan_values.get("follow_links", False)),
        retry_count=int(scan_values.get("retry_count", 1)),
    )
    return AppConfig(
        format_version=version,
        log_level=log_level,
        json_log=bool(logging_values.get("json", False)),
        scan=scan,
    )

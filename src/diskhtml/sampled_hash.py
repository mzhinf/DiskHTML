"""为大文件快速预检提供固定次数、目标读取量的 SHA-256 采样指纹。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Literal, Protocol, TypedDict

FULL_SHA256_ALGORITHM = "full-sha256"
DEFAULT_SAMPLE_TARGET_BYTES = 8 * 1024 * 1024
DEFAULT_SAMPLE_COUNT = 8
MAX_SAMPLE_COUNT = 32

_FORMAT_VERSION = b"diskhtml-sampled-sha256-v1"
_MEBIBYTE = 1024 * 1024
_MEBIBYTE_DECIMAL_PLACES = 20
_FULL_HASH_READ_SIZE = 1024 * 1024


class FileChangedDuringHashError(RuntimeError):
    """表示文件在完整哈希或采样指纹计算期间发生了变化。"""


class _HashUpdater(Protocol):
    """描述 hashlib 摘要对象使用的最小更新协议。"""

    def update(self, data: bytes, /) -> None:
        """把字节加入当前摘要。"""


class SampledHashResult(TypedDict):
    """描述完整哈希或采样指纹的结构化结果。"""

    mode: Literal["full", "sampled"]
    algorithm: str
    digest: str
    file_size: int
    sample_target_bytes: int
    sample_count: int
    actual_sample_count: int
    block_size: int
    sampled_bytes: int


def sampled_sha256_algorithm(
    sample_target_bytes: int = DEFAULT_SAMPLE_TARGET_BYTES,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
) -> str:
    """校验采样参数并返回稳定的采样算法标识。"""

    _validate_parameters(sample_target_bytes, sample_count)
    return f"sampled-sha256-{_target_megabytes_label(sample_target_bytes)}_{sample_count}"


def sampled_sha256(
    path: str | os.PathLike[str],
    sample_target_bytes: int = DEFAULT_SAMPLE_TARGET_BYTES,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
) -> SampledHashResult:
    """计算完整 SHA-256，或生成仅供快速预检使用的采样指纹。

    目标读取量内的文件按原始内容计算完整 SHA-256。超过目标读取量时固定使用请求的采样
    次数规划均匀数据块；偏移空间不足时会去重，并在结果中报告实际读取次数。
    """

    _validate_parameters(sample_target_bytes, sample_count)
    file_path = Path(path)
    before = os.stat(file_path)
    file_size = before.st_size

    try:
        if file_size <= sample_target_bytes:
            result = _full_sha256(file_path, file_size, sample_target_bytes, sample_count)
        else:
            result = _sampled_sha256(file_path, file_size, sample_target_bytes, sample_count)
    except FileChangedDuringHashError:
        _ensure_file_unchanged(file_path, before, os.stat(file_path))
        raise

    _ensure_file_unchanged(file_path, before, os.stat(file_path))
    return result


def _ensure_file_unchanged(
    path: Path,
    before: os.stat_result,
    after: os.stat_result,
) -> None:
    """比较文件大小和纳秒修改时间，拒绝保存不稳定结果。"""

    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise FileChangedDuringHashError(
            f"文件在哈希计算期间发生变化：{path} "
            f"（大小 {before.st_size} -> {after.st_size}，"
            f"修改时间 {before.st_mtime_ns} -> {after.st_mtime_ns}）。"
        )


def _validate_parameters(sample_target_bytes: int, sample_count: int) -> None:
    """拒绝会破坏固定目标读取量采样语义的参数。"""

    if isinstance(sample_target_bytes, bool) or not isinstance(sample_target_bytes, int):
        raise TypeError("sample_target_bytes 必须是大于 0 的整数（字节）。")
    if sample_target_bytes <= 0:
        raise ValueError("sample_target_bytes 必须大于 0。")
    if isinstance(sample_count, bool) or not isinstance(sample_count, int):
        raise TypeError(f"sample_count 必须是 2 到 {MAX_SAMPLE_COUNT} 之间的整数。")
    if sample_count < 2:
        raise ValueError("sample_count 必须大于或等于 2。")
    if sample_count > MAX_SAMPLE_COUNT:
        raise ValueError(f"sample_count 不得大于 {MAX_SAMPLE_COUNT}。")


def _full_sha256(
    path: Path,
    file_size: int,
    sample_target_bytes: int,
    requested_sample_count: int,
) -> SampledHashResult:
    """顺序读取完整文件，并返回标准 SHA-256 摘要。"""

    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        while block := handle.read(_FULL_HASH_READ_SIZE):
            digest.update(block)
    return {
        "mode": "full",
        "algorithm": FULL_SHA256_ALGORITHM,
        "digest": digest.hexdigest(),
        "file_size": file_size,
        "sample_target_bytes": sample_target_bytes,
        "sample_count": requested_sample_count,
        "actual_sample_count": 1,
        "block_size": file_size,
        "sampled_bytes": file_size,
    }


def _sampled_sha256(
    path: Path,
    file_size: int,
    sample_target_bytes: int,
    requested_sample_count: int,
) -> SampledHashResult:
    """按升序偏移读取均匀数据块，并生成自描述采样指纹。"""

    block_size = (sample_target_bytes + requested_sample_count - 1) // requested_sample_count
    offsets = _sample_offsets(file_size, block_size, requested_sample_count)
    algorithm = sampled_sha256_algorithm(sample_target_bytes, requested_sample_count)
    digest = hashlib.sha256()
    _update_field(digest, _FORMAT_VERSION)
    _update_field(digest, algorithm.encode("ascii"))
    _update_integer(digest, file_size)
    _update_integer(digest, sample_target_bytes)
    _update_integer(digest, requested_sample_count)
    _update_integer(digest, len(offsets))
    _update_integer(digest, block_size)

    sampled_bytes = 0
    short_read = False
    with path.open("rb", buffering=0) as handle:
        for offset in offsets:
            handle.seek(offset)
            block = handle.read(block_size)
            _update_integer(digest, offset)
            _update_integer(digest, len(block))
            _update_field(digest, block)
            sampled_bytes += len(block)
            short_read = short_read or len(block) != block_size

    if short_read:
        raise FileChangedDuringHashError(f"采样期间读取长度发生变化：{path}。")
    return {
        "mode": "sampled",
        "algorithm": algorithm,
        "digest": digest.hexdigest(),
        "file_size": file_size,
        "sample_target_bytes": sample_target_bytes,
        "sample_count": requested_sample_count,
        "actual_sample_count": len(offsets),
        "block_size": block_size,
        "sampled_bytes": sampled_bytes,
    }


def _sample_offsets(file_size: int, block_size: int, sample_count: int) -> tuple[int, ...]:
    """生成包含文件头尾、去重且升序的均匀采样偏移。"""

    last_offset = file_size - block_size
    divisor = sample_count - 1
    offsets = {(last_offset * index + divisor // 2) // divisor for index in range(sample_count)}
    return tuple(sorted(offsets))


def _target_megabytes_label(sample_target_bytes: int) -> str:
    """把目标字节数转换为无精度损失的 1024² 字节 MB 标识。"""

    whole, remainder = divmod(sample_target_bytes, _MEBIBYTE)
    if remainder == 0:
        return str(whole)
    decimal_numerator = remainder * 5**_MEBIBYTE_DECIMAL_PLACES
    fraction = f"{decimal_numerator:0{_MEBIBYTE_DECIMAL_PLACES}d}".rstrip("0")
    return f"{whole}.{fraction}"


def _update_integer(digest: _HashUpdater, value: int) -> None:
    """把整数按带长度前缀的十进制形式写入摘要。"""

    _update_field(digest, str(value).encode("ascii"))


def _update_field(digest: _HashUpdater, payload: bytes) -> None:
    """把任意字段按八字节长度前缀写入摘要，避免字段边界歧义。"""

    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)


__all__ = [
    "FULL_SHA256_ALGORITHM",
    "DEFAULT_SAMPLE_TARGET_BYTES",
    "DEFAULT_SAMPLE_COUNT",
    "MAX_SAMPLE_COUNT",
    "FileChangedDuringHashError",
    "SampledHashResult",
    "sampled_sha256",
    "sampled_sha256_algorithm",
]

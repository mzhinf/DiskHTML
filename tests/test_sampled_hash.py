"""固定次数、目标读取量 SHA-256 采样指纹测试。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from diskhtml.sampled_hash import (
    FileChangedDuringHashError,
    _sample_offsets,
    sampled_sha256,
)


class SampledSha256Tests(TestCase):
    """验证完整哈希与采样指纹的边界、稳定性和变化检测。"""

    def test_empty_file_uses_full_sha256(self) -> None:
        """空文件应返回标准完整 SHA-256，而不是采样指纹。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "empty.bin"
            path.write_bytes(b"")

            result = sampled_sha256(path)

        self.assertEqual(result["mode"], "full")
        self.assertEqual(result["algorithm"], "full-sha256")
        self.assertEqual(result["digest"], hashlib.sha256(b"").hexdigest())
        self.assertEqual(result["file_size"], 0)
        self.assertEqual(result["block_size"], 0)
        self.assertEqual(result["sampled_bytes"], 0)
        self.assertEqual(result["actual_sample_count"], 1)

    def test_file_smaller_than_target_uses_full_sha256(self) -> None:
        """小于目标读取量的文件应完整读取，摘要与标准库结果一致。"""

        payload = b"small-file"
        result = self._hash_payload(payload, sample_target_bytes=len(payload) + 1)

        self.assertEqual(result["mode"], "full")
        self.assertEqual(result["algorithm"], "full-sha256")
        self.assertEqual(result["digest"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(result["sampled_bytes"], len(payload))

    def test_file_equal_to_target_uses_full_sha256(self) -> None:
        """恰好等于目标读取量的文件仍应计算完整 SHA-256。"""

        payload = b"equal-target"
        result = self._hash_payload(payload, sample_target_bytes=len(payload))

        self.assertEqual(result["mode"], "full")
        self.assertEqual(result["digest"], hashlib.sha256(payload).hexdigest())

    def test_large_file_uses_fixed_sample_count_and_target_derived_block(self) -> None:
        """大文件应按请求次数读取，并用向上取整值作为数据块大小。"""

        payload = bytes(range(64))
        result = self._hash_payload(payload, sample_target_bytes=17, sample_count=4)

        self.assertEqual(result["mode"], "sampled")
        self.assertEqual(result["sample_count"], 4)
        self.assertEqual(result["actual_sample_count"], 4)
        self.assertEqual(result["block_size"], 5)
        self.assertEqual(result["sampled_bytes"], 20)

    def test_default_algorithm_name_uses_megabyte_budget(self) -> None:
        """默认八 MB、八次采样应使用约定的算法标识。"""

        target_bytes = 8 * 1024 * 1024
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "large.bin"
            with path.open("wb") as handle:
                handle.seek(target_bytes)
                handle.write(b"\0")

            result = sampled_sha256(path)

        self.assertEqual(result["algorithm"], "sampled-sha256-8_8")

    def test_head_middle_and_tail_changes_affect_sampled_fingerprint(self) -> None:
        """被均匀覆盖的文件头、中间和尾部变化都应改变指纹。"""

        payload = bytearray(range(30))
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "sampled.bin"
            path.write_bytes(payload)
            baseline = sampled_sha256(path, sample_target_bytes=9, sample_count=3)["digest"]

            for offset in (0, len(payload) // 2, len(payload) - 1):
                changed = payload.copy()
                changed[offset] ^= 0xFF
                path.write_bytes(changed)
                digest = sampled_sha256(path, sample_target_bytes=9, sample_count=3)["digest"]
                self.assertNotEqual(digest, baseline, f"偏移 {offset} 的变化未影响指纹")

    def test_offsets_are_unique_sorted_and_include_both_ends(self) -> None:
        """采样偏移必须去重、升序，并明确包含文件头和文件尾。"""

        file_size = 100
        block_size = 7
        offsets = _sample_offsets(file_size, block_size, sample_count=8)

        self.assertEqual(offsets, tuple(sorted(set(offsets))))
        self.assertEqual(len(offsets), 8)
        self.assertEqual(offsets[0], 0)
        self.assertEqual(offsets[-1], file_size - block_size)

    def test_tiny_offset_space_is_deduplicated_and_reported(self) -> None:
        """唯一偏移不足时不得重复寻道，结果应报告实际采样次数。"""

        result = self._hash_payload(b"ab", sample_target_bytes=1, sample_count=8)

        self.assertEqual(result["sample_count"], 8)
        self.assertEqual(result["actual_sample_count"], 2)
        self.assertEqual(result["sampled_bytes"], 2)

    def test_result_is_stable_for_unchanged_file(self) -> None:
        """相同文件和配置重复计算应得到完全相同的结构化结果。"""

        payload = bytes(range(100))
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "stable.bin"
            path.write_bytes(payload)

            first = sampled_sha256(path, sample_target_bytes=24, sample_count=6)
            second = sampled_sha256(path, sample_target_bytes=24, sample_count=6)

        self.assertEqual(first, second)

    def test_file_size_is_part_of_sampled_hash_input(self) -> None:
        """采样内容相同但文件大小不同的文件不得产生相同指纹。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            shorter = root / "shorter.bin"
            longer = root / "longer.bin"
            shorter.write_bytes(b"\0" * 40)
            longer.write_bytes(b"\0" * 41)

            first = sampled_sha256(shorter, sample_target_bytes=8, sample_count=4)
            second = sampled_sha256(longer, sample_target_bytes=8, sample_count=4)

        self.assertNotEqual(first["digest"], second["digest"])

    def test_invalid_parameters_raise_clear_errors(self) -> None:
        """目标读取量和次数的类型、下界及上界都应明确拒绝。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "input.bin"
            path.write_bytes(b"data")

            for target_bytes in (0, -1):
                with self.subTest(sample_target_bytes=target_bytes):
                    with self.assertRaisesRegex(ValueError, "sample_target_bytes"):
                        sampled_sha256(path, sample_target_bytes=target_bytes)
            for target_bytes in (True, 1.5):
                with self.subTest(sample_target_bytes=target_bytes):
                    with self.assertRaisesRegex(TypeError, "sample_target_bytes"):
                        sampled_sha256(  # type: ignore[arg-type]
                            path,
                            sample_target_bytes=target_bytes,
                        )
            for count in (1, 33):
                with self.subTest(sample_count=count):
                    with self.assertRaisesRegex(ValueError, "sample_count"):
                        sampled_sha256(path, sample_count=count)
            for count in (False, 2.5):
                with self.subTest(sample_count=count):
                    with self.assertRaisesRegex(TypeError, "sample_count"):
                        sampled_sha256(path, sample_count=count)  # type: ignore[arg-type]

    def test_change_during_calculation_raises_clear_error(self) -> None:
        """前后大小或纳秒修改时间不同时必须报错，不能返回指纹。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "changing.bin"
            path.write_bytes(bytes(range(64)))
            before = os.stat(path)
            changed_metadata = (
                SimpleNamespace(
                    st_size=before.st_size + 1,
                    st_mtime_ns=before.st_mtime_ns,
                ),
                SimpleNamespace(
                    st_size=before.st_size,
                    st_mtime_ns=before.st_mtime_ns + 1,
                ),
            )

            for after in changed_metadata:
                with self.subTest(after=after):
                    with patch("diskhtml.sampled_hash.os.stat", side_effect=(before, after)):
                        with self.assertRaisesRegex(FileChangedDuringHashError, "发生变化"):
                            sampled_sha256(path, sample_target_bytes=16, sample_count=4)

    def _hash_payload(
        self,
        payload: bytes,
        *,
        sample_target_bytes: int,
        sample_count: int = 8,
    ) -> dict[str, object]:
        """在隔离临时目录中计算指定内容的结果。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "input.bin"
            path.write_bytes(payload)
            return sampled_sha256(
                path,
                sample_target_bytes=sample_target_bytes,
                sample_count=sample_count,
            )


if __name__ == "__main__":
    from unittest import main

    main()

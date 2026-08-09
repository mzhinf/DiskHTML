"""配置格式、兼容名称与默认值测试。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from diskhtml.config import HashMode, ScanConfig, load_config
from diskhtml.sampled_hash import sampled_sha256_algorithm


class ConfigTests(TestCase):
    """验证配置版本和边界条件。"""

    def test_default_config_is_bounded(self) -> None:
        """默认配置必须使用正数工作线程、队列和读取块。"""

        config = load_config(None)
        self.assertGreaterEqual(config.scan.workers, 1)
        self.assertGreaterEqual(config.scan.queue_size, 1)
        self.assertGreaterEqual(config.scan.chunk_size, 1)
        self.assertEqual(HashMode.FULL, config.scan.hash_mode)

    def test_load_toml(self) -> None:
        """TOML 中的扫描和日志值应被转换为强类型对象。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                'format_version = 1\n[logging]\nlevel = "debug"\n'
                '[scan]\nworkers = 3\nexclude_extensions = ["tmp"]\n',
                encoding="utf-8",
            )
            config = load_config(path)
        self.assertEqual(config.log_level, "DEBUG")
        self.assertEqual(config.scan.workers, 3)
        self.assertEqual(config.scan.exclude_extensions, ("tmp",))

    def test_load_sampled_hash_strategy(self) -> None:
        """TOML 应读取目标采样量和固定次数的采样策略。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                'format_version = 1\n[scan]\nhash_mode = "sampled"\n'
                "sample_target_bytes = 16777216\nsample_count = 12\n",
                encoding="utf-8",
            )
            config = load_config(path).scan

        self.assertEqual(HashMode.SAMPLED, config.hash_mode)
        self.assertEqual(16 * 1024 * 1024, config.sample_target_bytes)
        self.assertEqual("sampled-sha256-16_12", config.requested_hash_algorithm())
        self.assertEqual(
            sampled_sha256_algorithm(16 * 1024 * 1024, 12),
            config.requested_hash_algorithm(),
        )

    def test_invalid_scan_config_is_rejected(self) -> None:
        """无界或无效配置不能进入扫描器。"""

        with self.assertRaisesRegex(ValueError, "线程数"):
            ScanConfig(workers=0)
        with self.assertRaisesRegex(ValueError, "sample_target_bytes"):
            ScanConfig(sample_target_bytes=0)
        with self.assertRaisesRegex(ValueError, "sample_count"):
            ScanConfig(sample_count=33)
        with self.assertRaisesRegex(ValueError, "SHA-512"):
            ScanConfig(hash_mode=HashMode.SAMPLED, sha512=True)

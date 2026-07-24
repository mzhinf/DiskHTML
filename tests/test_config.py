"""配置格式与默认值测试。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from diskhtml.config import ScanConfig, load_config


class ConfigTests(TestCase):
    """验证配置版本和边界条件。"""

    def test_default_config_is_bounded(self) -> None:
        """默认配置必须使用正数工作线程、队列和读取块。"""

        config = load_config(None)
        self.assertGreaterEqual(config.scan.workers, 1)
        self.assertGreaterEqual(config.scan.queue_size, 1)
        self.assertGreaterEqual(config.scan.chunk_size, 1)

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

    def test_invalid_scan_config_is_rejected(self) -> None:
        """无界或无效配置不能进入扫描器。"""

        with self.assertRaisesRegex(ValueError, "线程数"):
            ScanConfig(workers=0)

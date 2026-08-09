"""高级 CLI 与 EXE CLI 共享扫描参数的等价测试。"""

from __future__ import annotations

import argparse
from unittest import TestCase

from diskhtml._cli_options import add_scan_options, merge_scan_config
from diskhtml.config import HashMode, ScanConfig


class CliOptionTests(TestCase):
    """验证公共参数只声明和合并一次，并保留入口差异。"""

    def test_common_overrides_produce_equal_config(self) -> None:
        """相同公共参数应为两套入口生成完全相同的扫描配置。"""

        defaults = ScanConfig(
            workers=2,
            queue_size=4,
            chunk_size=8,
            sample_target_bytes=16,
            sample_count=4,
        )
        arguments = [
            "--workers",
            "3",
            "--queue-size",
            "5",
            "--chunk-size",
            "9",
            "--sha512",
            "--follow-links",
        ]
        results = []
        for _entry in ("advanced", "executable"):
            parser = argparse.ArgumentParser()
            add_scan_options(parser, include_hash_strategy=False)
            results.append(merge_scan_config(defaults, parser.parse_args(arguments)))

        self.assertEqual(results[0], results[1])
        self.assertEqual(3, results[0].workers)
        self.assertEqual(5, results[0].queue_size)
        self.assertEqual(9, results[0].chunk_size)
        self.assertTrue(results[0].sha512)
        self.assertTrue(results[0].follow_links)
        self.assertEqual(HashMode.FULL, results[0].hash_mode)
        self.assertEqual(16, results[0].sample_target_bytes)
        self.assertEqual(4, results[0].sample_count)

    def test_optional_hash_strategy_is_merged_when_exposed(self) -> None:
        """高级入口可覆盖 Hash 策略，未暴露该参数的入口保留配置默认值。"""

        defaults = ScanConfig()
        parser = argparse.ArgumentParser()
        add_scan_options(parser)
        self.assertIn("--sample-target-bytes", parser.format_help())
        merged = merge_scan_config(
            defaults,
            parser.parse_args(
                [
                    "--hash-mode",
                    "sampled",
                    "--sample-target-bytes",
                    "32",
                    "--sample-count",
                    "4",
                ]
            ),
        )

        self.assertEqual(HashMode.SAMPLED, merged.hash_mode)
        self.assertEqual(32, merged.sample_target_bytes)
        self.assertEqual(4, merged.sample_count)

        restricted = argparse.ArgumentParser()
        add_scan_options(restricted, include_hash_strategy=False)
        restricted_defaults = ScanConfig(
            hash_mode=HashMode.SAMPLED, sample_target_bytes=16, sample_count=4
        )
        self.assertEqual(
            restricted_defaults,
            merge_scan_config(restricted_defaults, restricted.parse_args([])),
        )

    def test_boolean_defaults_can_only_be_enabled(self) -> None:
        """布尔开关继续沿用“命令行启用或配置默认启用”的兼容语义。"""

        parser = argparse.ArgumentParser()
        add_scan_options(parser, include_hash_strategy=False)
        arguments = parser.parse_args([])

        self.assertFalse(merge_scan_config(ScanConfig(), arguments).sha512)
        self.assertTrue(merge_scan_config(ScanConfig(sha512=True), arguments).sha512)
        self.assertFalse(merge_scan_config(ScanConfig(), arguments).follow_links)
        self.assertTrue(merge_scan_config(ScanConfig(follow_links=True), arguments).follow_links)


if __name__ == "__main__":
    import unittest

    unittest.main()

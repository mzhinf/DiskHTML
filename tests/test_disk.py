"""Windows 卷与物理磁盘信息采集测试。"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from diskhtml import disk


class DiskInfoTests(TestCase):
    """验证硬件信息采集与安全降级，不读取真实硬件数据。"""

    def test_windows_volume_and_disk_fields_are_stored(self) -> None:
        """模拟 Windows 成功返回时应保留卷、分区和物理磁盘字段。"""

        def volume_fields(_anchor: str, result: dict[str, object]) -> None:
            result["volume_guid"] = "\\\\?\\Volume{test}\\"
            result["volume_label"] = "测试卷"
            result["filesystem"] = "NTFS"

        def disk_fields(result: dict[str, object]) -> None:
            result["disk_model"] = "模拟磁盘"
            result["disk_serial"] = "模拟序列号"
            result["partition_json"] = json.dumps([{"DiskNumber": 0}], ensure_ascii=False)

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            source = Path(directory)
            with (
                patch.object(disk.os, "name", "nt"),
                patch.object(disk, "_collect_windows_volume_fields", volume_fields),
                patch.object(disk, "_collect_windows_disk_fields", disk_fields),
            ):
                result = disk.collect_volume_info(source)

        self.assertEqual(result["volume_label"], "测试卷")
        self.assertEqual(result["filesystem"], "NTFS")
        self.assertEqual(result["disk_model"], "模拟磁盘")
        self.assertEqual(result["disk_serial"], "模拟序列号")
        self.assertEqual(result["capture_error"], None)

    def test_disk_collection_failure_is_saved_without_aborting_scan(self) -> None:
        """物理磁盘采集失败时应保存明确原因而非抛出异常。"""

        def volume_fields(_anchor: str, result: dict[str, object]) -> None:
            result["filesystem"] = "NTFS"

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            source = Path(directory)
            with (
                patch.object(disk.os, "name", "nt"),
                patch.object(disk, "_collect_windows_volume_fields", volume_fields),
                patch.object(
                    disk,
                    "_collect_windows_disk_fields",
                    side_effect=OSError("模拟权限不足"),
                ),
            ):
                result = disk.collect_volume_info(source)

        self.assertEqual(result["filesystem"], "NTFS")
        self.assertIn("物理磁盘信息采集失败", result["capture_error"])

"""已核验上游许可证来源的完整性测试。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest import TestCase


class LicenseSourceTests(TestCase):
    """防止版本固定的法律来源文件被静默替换。"""

    def test_provenance_hashes_match_cached_sources(self) -> None:
        """每个登记来源必须存在并与记录的 SHA-256 一致。"""

        root = Path(__file__).parent.parent / "third_party" / "license_sources" / "upstream"
        provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(1, provenance["format_version"])
        self.assertIn("许可证", provenance["purpose"])
        self.assertGreaterEqual(len(provenance["sources"]), 10)
        for source in provenance["sources"]:
            payload = (root / source["file"]).read_bytes()
            self.assertEqual(source["sha256"], hashlib.sha256(payload).hexdigest().upper())
            self.assertIn("https://", source["source_url"])
            self.assertIn(source["priority"], {1, 2, 3, 4})
            self.assertTrue(source["components"])
            self.assertTrue(source["status"])

    def test_microsoft_original_and_text_copy_are_both_registered(self) -> None:
        """微软专有条款必须同时保留官方原始 DOCX 与可读文本。"""

        root = Path(__file__).parent.parent / "third_party" / "license_sources" / "upstream"
        provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
        names = {item["file"] for item in provenance["sources"]}
        self.assertIn("Microsoft-Visual-Cpp-Runtime-2015-2022.docx", names)
        self.assertIn("Microsoft-Visual-Cpp-Runtime-2015-2022.txt", names)

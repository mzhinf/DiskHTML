"""发布清单脚本的端到端测试。"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


class ReleaseManifestScriptTests(TestCase):
    """验证发布清单记录可执行文件和发布目录的可复核信息。"""

    def test_manifest_records_executable_hash_and_package_size(self) -> None:
        """脚本应为发布目录写入 SHA256、大小和文件计数。"""

        project_root = Path(__file__).parent.parent
        script = project_root / "scripts" / "create_release_manifest.py"
        payload = b"DiskHTML release test"
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            package = root / "DiskHTML"
            package.mkdir()
            (package / "DiskHTML.exe").write_bytes(payload)
            (package / "runtime.dat").write_bytes(b"runtime")
            output = root / "release-manifest.json"

            subprocess.run(
                [sys.executable, str(script), str(package), str(output)],
                cwd=project_root,
                check=True,
                capture_output=True,
                text=True,
            )
            manifest = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(manifest["package_name"], "DiskHTML")
        self.assertEqual(manifest["package_file_count"], 2)
        self.assertEqual(manifest["package_bytes"], len(payload) + len(b"runtime"))
        self.assertEqual(
            manifest["executable"]["sha256"], hashlib.sha256(payload).hexdigest().upper()
        )

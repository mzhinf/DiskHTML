"""压力数据集生成脚本的端到端测试。"""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


class StressDatasetScriptTests(TestCase):
    """验证压力数据集脚本生成可复核的目录和清单。"""

    def test_generator_creates_expected_files_and_manifest(self) -> None:
        """小规模调用应按目录扇出创建文件并写入准确清单。"""

        project_root = Path(__file__).parent.parent
        script = project_root / "scripts" / "generate_stress_dataset.py"
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            output = Path(directory) / "dataset"
            subprocess.run(
                [
                    sys.executable,
                    str(script),
                    str(output),
                    "--files",
                    "5",
                    "--size-bytes",
                    "32",
                    "--files-per-directory",
                    "2",
                    "--progress-every",
                    "2",
                ],
                cwd=project_root,
                check=True,
                capture_output=True,
                text=True,
            )
            manifest = json.loads((output / "dataset.json").read_text(encoding="utf-8"))
            files = tuple(output.glob("batch-*/*.bin"))
            file_sizes = {path.stat().st_size for path in files}

        self.assertEqual(manifest["files"], 5)
        self.assertEqual(manifest["directories"], 3)
        self.assertEqual(len(files), 5)
        self.assertEqual(file_sizes, {32})

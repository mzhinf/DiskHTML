"""扫描性能基准脚本的端到端测试。"""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


class BenchmarkScriptTests(TestCase):
    """验证基准脚本生成完整且可解析的结果目录。"""

    def test_benchmark_script_generates_metrics_and_report(self) -> None:
        """小样本运行应写入扫描、报告、存储和内存指标。"""

        project_root = Path(__file__).parent.parent
        script = project_root / "scripts" / "benchmark_scan.py"
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "alpha.txt").write_text("alpha", encoding="utf-8")
            (source / "beta.txt").write_text("beta", encoding="utf-8")
            output = root / "benchmark"

            subprocess.run(
                [
                    sys.executable,
                    str(script),
                    str(source),
                    str(output),
                    "--workers",
                    "1",
                    "--queue-size",
                    "1",
                ],
                cwd=project_root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = json.loads((output / "result.json").read_text(encoding="utf-8"))

        self.assertEqual(result["scan"]["files_hashed"], 2)
        self.assertGreater(result["storage"]["database_bytes"], 0)
        self.assertGreater(result["storage"]["report_bytes"], 0)
        self.assertIsNotNone(result["memory"]["peak_working_set_bytes"])
        self.assertEqual(result["validation"]["project_check"], "ok")

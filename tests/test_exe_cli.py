"""DiskHTML.exe 精简命令行入口测试。"""

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from diskhtml.config import load_config
from diskhtml.exe_cli import main


class ExeCliTests(TestCase):
    """验证 EXE 参数可生成和比较 HTML，不依赖 SQLite 项目命令。"""

    def test_backup_and_compare_html(self) -> None:
        """EXE 命令入口应按用户提供的备份流程产生 HTML 文件。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            old_source = root / "old"
            new_source = root / "new"
            old_source.mkdir()
            new_source.mkdir()
            (old_source / "same.txt").write_text("相同", encoding="utf-8")
            (new_source / "same.txt").write_text("相同", encoding="utf-8")
            (new_source / "added.txt").write_text("新增", encoding="utf-8")
            old_archive = root / "old.html"
            new_archive = root / "new.html"
            comparison = root / "comparison.html"

            self.assertEqual(main(["snapshot", str(old_source), str(old_archive)]), 0)
            self.assertEqual(main(["snapshot", str(new_source), str(new_archive)]), 0)
            self.assertEqual(
                main(["compare-source", str(old_archive), ".", str(new_source), str(comparison)]),
                0,
            )

            self.assertTrue(old_archive.is_file())
            self.assertTrue(new_archive.is_file())
            self.assertTrue(comparison.is_file())
            self.assertIn('id="same-heading"', comparison.read_text(encoding="utf-8"))

    def test_backup_rejects_existing_html(self) -> None:
        """EXE 命令入口不得覆盖已有快照。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            output = root / "backup.html"
            output.write_text("旧文件", encoding="utf-8")

            error = StringIO()
            with redirect_stderr(error):
                self.assertEqual(main(["snapshot", str(source), str(output)]), 2)
            self.assertIn("输出 HTML 已存在", error.getvalue())

    def test_default_config_is_loaded_and_explicit_config_overrides_it(self) -> None:
        """EXE 同目录配置默认生效，显式 --config 应保持更高优先级。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            example = Path(__file__).parents[1] / "config.example.toml"
            original = example.read_text(encoding="utf-8")
            example_workers = load_config(example).scan.workers
            default_workers = example_workers + 1
            explicit_workers = example_workers + 2
            default_config = root / "config.toml"
            explicit_config = root / "explicit.toml"
            default_config.write_text(
                original.replace(
                    f"workers = {example_workers}",
                    f"workers = {default_workers}",
                ),
                encoding="utf-8",
            )
            explicit_config.write_text(
                original.replace(
                    f"workers = {example_workers}",
                    f"workers = {explicit_workers}",
                ),
                encoding="utf-8",
            )
            source = root / "source"
            source.mkdir()
            output = root / "snapshot.html"

            with patch("diskhtml.exe_cli.create_html_snapshot", return_value=output) as create:
                self.assertEqual(
                    main(
                        ["snapshot", str(source), str(output)],
                        default_config=default_config,
                    ),
                    0,
                )
                self.assertEqual(default_workers, create.call_args.args[2].workers)

                self.assertEqual(
                    main(
                        [
                            "--config",
                            str(explicit_config),
                            "snapshot",
                            str(source),
                            str(output),
                        ],
                        default_config=default_config,
                    ),
                    0,
                )
                self.assertEqual(explicit_workers, create.call_args.args[2].workers)

"""命令行帮助和数据库维护命令测试。"""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from diskhtml.cli import main


class CliTests(TestCase):
    """验证可安装入口的最小闭环。"""

    def test_no_command_prints_help(self) -> None:
        """不带子命令时应显示中文帮助并成功退出。"""

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main([])
        self.assertEqual(exit_code, 0)
        self.assertIn("冷备份校验工具", output.getvalue())
        self.assertIn("选项", output.getvalue())
        self.assertNotIn("options:", output.getvalue())
        self.assertNotIn("show this help message", output.getvalue())

    def test_init_and_check_database(self) -> None:
        """CLI 应能创建数据库并执行完整性检查。"""

        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "archive.sqlite3"
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["init-db", str(path)]), 0)
                self.assertEqual(main(["check-db", str(path)]), 0)
            self.assertTrue(path.exists())
            self.assertIn("数据库完整性检查：ok", output.getvalue())

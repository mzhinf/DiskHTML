"""DiskHTML 命令行入口与阶段 1 数据库维护命令。"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .config import load_config
from .database import Database
from .logging_config import configure_logging


class ChineseArgumentParser(argparse.ArgumentParser):
    """把 argparse 固定输出本地化为中文。"""

    def format_usage(self) -> str:
        """返回中文用法标题。"""

        return super().format_usage().replace("usage:", "用法：", 1)

    def format_help(self) -> str:
        """返回中文帮助标题。"""

        return super().format_help().replace("usage:", "用法：", 1)

    def error(self, message: str) -> None:
        """以中文标签报告参数错误并退出。"""

        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: 错误：{message}\n")


def build_parser() -> argparse.ArgumentParser:
    """构造可供测试和后续子命令扩展的参数解析器。"""

    parser = ChineseArgumentParser(
        prog="diskhtml",
        description="Windows 文件 Hash 冷备份校验工具",
        add_help=False,
    )
    parser._positionals.title = "位置参数"
    parser._optionals.title = "选项"
    parser.add_argument("-h", "--help", action="help", help="显示帮助信息并退出")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="显示版本信息并退出",
    )
    parser.add_argument("--config", type=Path, help="TOML 配置文件路径")
    subparsers = parser.add_subparsers(dest="command", title="命令")

    init_parser = subparsers.add_parser("init-db", help="创建或迁移项目数据库")
    init_parser.add_argument("database", type=Path, help="SQLite 数据库路径")

    check_parser = subparsers.add_parser("check-db", help="执行数据库完整性检查")
    check_parser.add_argument("database", type=Path, help="SQLite 数据库路径")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """执行命令并返回稳定退出码。"""

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    try:
        config = load_config(args.config)
        configure_logging(config.log_level, config.json_log)
        database = Database(args.database)
        try:
            if args.command == "init-db":
                print(f"数据库已就绪：{args.database}")
                return 0
            result = database.integrity_check()
            print(f"数据库完整性检查：{result}")
            return 0 if result == "ok" else 2
        finally:
            database.close()
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 2

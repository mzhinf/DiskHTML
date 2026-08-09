"""DiskHTML.exe 的精简命令行入口。"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from ._cli_options import add_scan_options, merge_scan_config
from .config import load_config
from .html_archive import (
    compare_html_directory_to_source,
    create_html_snapshot,
    render_html_snapshot_from_sqlite,
)


def build_parser() -> argparse.ArgumentParser:
    """构建仅包含 HTML 快照工作流的 EXE 参数解析器。"""

    parser = argparse.ArgumentParser(
        prog="DiskHTML",
        description="生成和比较可离线打开的 HTML 快照。",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, help="TOML 扫描配置文件")
    commands = parser.add_subparsers(dest="command", required=True)

    snapshot = commands.add_parser("snapshot", help="扫描目录或文件并生成单文件 HTML 快照")
    snapshot.add_argument("source", type=Path, help="扫描源路径")
    snapshot.add_argument("output", type=Path, help="新的 .html 快照")
    add_scan_options(snapshot, include_hash_strategy=False)

    render = commands.add_parser("render-sqlite", help="从 SQLite 快照索引重新生成当前版本 HTML")
    render.add_argument("database", type=Path, help="历史 .sqlite3 快照索引")
    render.add_argument("output", type=Path, help="新的 .html 快照")

    compare = commands.add_parser("compare-source", help="将 HTML 快照中选定目录与本机目录比较")
    compare.add_argument("archive", type=Path, help="历史快照 .html")
    compare.add_argument("archived_directory", help="HTML 快照中的相对目录，根目录使用 .")
    compare.add_argument("source", type=Path, help="本机当前目录")
    compare.add_argument("output", type=Path, help="新的 .html 比较报告")
    add_scan_options(compare, include_hash_strategy=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """执行 EXE 支持的 HTML 快照或 HTML 比较命令。"""

    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "snapshot":
            output = create_html_snapshot(
                args.source, args.output, merge_scan_config(config.scan, args)
            )
            _print(f"HTML 快照及 SQLite 索引已生成：{output}")
            return 0
        if args.command == "render-sqlite":
            output = render_html_snapshot_from_sqlite(args.database, args.output)
            _print(f"HTML 快照已从 SQLite 生成：{output}")
            return 0
        output = compare_html_directory_to_source(
            args.archive,
            args.archived_directory,
            args.source,
            args.output,
            merge_scan_config(config.scan, args),
        )
        _print(f"HTML 比较报告已生成：{output}")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        _print(f"错误：{exc}", error=True)
        return 2


def _print(message: str, *, error: bool = False) -> None:
    """在可用控制台中输出结果，不让无控制台 EXE 因输出失败。"""

    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        print(message, file=stream)

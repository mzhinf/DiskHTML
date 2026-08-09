"""DiskHTML 命令行入口与阶段 1 数据库维护命令。"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from . import __version__
from .compare import compare_scans, compare_sources
from .config import AppConfig, HashMode, ScanConfig, load_config
from .database import Database
from .html_archive import (
    compare_html_archives,
    compare_html_directory_to_source,
    create_html_snapshot,
    render_html_snapshot_from_sqlite,
)
from .logging_config import configure_logging
from .report import export_compare, export_scan
from .scanner import Scanner


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
        description="Windows 文件 Hash 快照与离线 HTML 比对工具",
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
    project_check_parser = subparsers.add_parser("check-project", help="执行项目数据自校验")
    project_check_parser.add_argument("database", type=Path, help="SQLite 数据库路径")

    scan_parser = subparsers.add_parser("scan", help="扫描文件、目录或卷")
    scan_parser.add_argument("database", type=Path, help="SQLite 数据库路径")
    scan_parser.add_argument("source", type=Path, help="扫描源路径")
    _add_scan_options(scan_parser)
    snapshot_parser = subparsers.add_parser("snapshot", help="扫描目录或文件并生成单文件 HTML 快照")
    snapshot_parser.add_argument("source", type=Path, help="扫描源路径")
    snapshot_parser.add_argument("output", type=Path, help="新的 .html 快照")
    _add_scan_options(snapshot_parser)

    render_sqlite_parser = subparsers.add_parser(
        "render-sqlite", help="从 SQLite 快照索引重新生成当前版本 HTML"
    )
    render_sqlite_parser.add_argument("database", type=Path, help="历史 .sqlite3 快照索引")
    render_sqlite_parser.add_argument("output", type=Path, help="新的 .html 快照")

    compare_source_parser = subparsers.add_parser(
        "compare-source", help="将 HTML 快照中的目录与本机目录比较并生成单文件 HTML 报告"
    )
    compare_source_parser.add_argument("archive", type=Path, help="历史 .html 快照")
    compare_source_parser.add_argument("archived_directory", help="快照中选择的目录；根目录使用 .")
    compare_source_parser.add_argument("source", type=Path, help="本机当前目录")
    compare_source_parser.add_argument("output", type=Path, help="新的 .html 比较报告")
    _add_scan_options(compare_source_parser, include_hash_strategy=False)

    compare_html_parser = subparsers.add_parser(
        "compare-html", help="比较两个 HTML 快照并生成单文件 HTML 报告"
    )
    compare_html_parser.add_argument("left", type=Path, help="左侧旧快照 .html")
    compare_html_parser.add_argument("right", type=Path, help="右侧新快照 .html")
    compare_html_parser.add_argument("output", type=Path, help="新的 .html 比较报告")

    resume_parser = subparsers.add_parser("resume", help="恢复未完成扫描")
    resume_parser.add_argument("database", type=Path, help="SQLite 数据库路径")
    resume_parser.add_argument("scan_id", help="扫描任务标识")

    status_parser = subparsers.add_parser("status", help="显示扫描任务状态")
    status_parser.add_argument("database", type=Path, help="SQLite 数据库路径")
    status_parser.add_argument("scan_id", nargs="?", help="扫描任务标识；省略时显示全部任务")

    export_parser = subparsers.add_parser("export", help="导出扫描或比较报告")
    export_parser.add_argument("database", type=Path, help="SQLite 数据库路径")
    export_parser.add_argument("task_id", help="扫描或比较任务标识")
    export_parser.add_argument("output", type=Path, help="新建的报告目录")
    export_parser.add_argument("--compare", action="store_true", help="导出比较报告")

    compare_parser = subparsers.add_parser("compare", help="比较两个当前文件或目录")
    compare_parser.add_argument("database", type=Path, help="SQLite 数据库路径")
    compare_parser.add_argument("left", type=Path, help="左侧旧源路径")
    compare_parser.add_argument("right", type=Path, help="右侧新源路径")
    _add_scan_options(compare_parser)

    verify_parser = subparsers.add_parser("verify", help="用当前路径复验历史扫描")
    verify_parser.add_argument("database", type=Path, help="SQLite 数据库路径")
    verify_parser.add_argument("scan_id", help="历史扫描任务标识")
    verify_parser.add_argument("source", type=Path, help="当前复验源路径")
    _add_scan_options(verify_parser)

    import_parser = subparsers.add_parser("import", help="导入已有项目数据库")
    import_parser.add_argument("database", type=Path, help="新建或覆盖的目标数据库路径")
    import_parser.add_argument("source", type=Path, help="已有项目数据库路径")
    return parser


def _add_scan_options(
    parser: argparse.ArgumentParser, *, include_hash_strategy: bool = True
) -> None:
    """为扫描类命令添加有界资源和摘要选项。"""

    parser.add_argument("--workers", type=int, help="Hash 工作线程数")
    parser.add_argument("--queue-size", type=int, help="有界任务队列大小")
    parser.add_argument("--chunk-size", type=int, help="每次读取的字节数")
    parser.add_argument("--sha512", action="store_true", help="额外计算 SHA512")
    parser.add_argument("--follow-links", action="store_true", help="跟随软链接和 Windows 重解析点")
    if include_hash_strategy:
        parser.add_argument(
            "--hash-mode",
            choices=tuple(mode.value for mode in HashMode),
            help="SHA-256 计算模式：full 或 sampled",
        )
        parser.add_argument("--sample-budget", type=int, help="采样读取总预算，单位为字节")
        parser.add_argument("--sample-count", type=int, help="固定采样次数，范围为 2 到 32")


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
        html_exit_code = _run_html_command(args, config)
        if html_exit_code is not None:
            return html_exit_code
        return _run_database_command(args, config, parser)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 2


def _run_html_command(args: argparse.Namespace, config: AppConfig) -> int | None:
    """执行不需要项目数据库的 HTML 快照、重渲染和比较命令。"""

    if args.command == "snapshot":
        output = create_html_snapshot(args.source, args.output, _scan_options(config.scan, args))
        print(f"HTML 快照已生成：{output}")
        return 0
    if args.command == "render-sqlite":
        output = render_html_snapshot_from_sqlite(args.database, args.output)
        print(f"HTML 快照已从 SQLite 生成：{output}")
        return 0
    if args.command == "compare-source":
        output = compare_html_directory_to_source(
            args.archive,
            args.archived_directory,
            args.source,
            args.output,
            _scan_options(config.scan, args),
        )
        print(f"HTML 目录比较报告已生成：{output}")
        return 0
    if args.command == "compare-html":
        output = compare_html_archives(args.left, args.right, args.output)
        print(f"HTML 比较报告已生成：{output}")
        return 0
    return None


def _run_database_command(
    args: argparse.Namespace, config: AppConfig, parser: argparse.ArgumentParser
) -> int:
    """打开项目数据库并执行扫描、维护、导出或比较命令。"""

    with Database(args.database) as database:
        if args.command == "init-db":
            print(f"数据库已就绪：{args.database}")
            return 0
        if args.command == "check-db":
            result = database.integrity_check()
            print(f"数据库完整性检查：{result}")
            return 0 if result == "ok" else 2
        if args.command == "check-project":
            return _print_project_check(database)
        if args.command == "scan":
            scan_id = Scanner(database).start(args.source, _scan_options(config.scan, args))
            print(f"扫描已完成：{scan_id}")
            return 0
        if args.command == "resume":
            Scanner(database).resume(args.scan_id)
            print(f"扫描已恢复并完成：{args.scan_id}")
            return 0
        if args.command == "status":
            return _print_scan_status(database, args.scan_id)
        if args.command == "export":
            output = (
                export_compare(database, args.task_id, args.output)
                if args.compare
                else export_scan(database, args.task_id, args.output)
            )
            print(f"报告已导出：{output}")
            return 0
        if args.command == "compare":
            compare_id = compare_sources(
                database, str(args.left), str(args.right), _scan_options(config.scan, args)
            )
            print(f"比较已完成：{compare_id}")
            return 0
        if args.command == "verify":
            current = Scanner(database).start(args.source, _scan_options(config.scan, args))
            compare_id = compare_scans(database, args.scan_id, current)
            print(f"复验已完成：{compare_id}")
            return 0
        if args.command == "import":
            _import_database(database, args.source, args.database)
            print(f"项目数据库已导入：{args.source} -> {args.database}")
            return 0
    parser.error(f"未知命令：{args.command}")
    return 2


def _print_project_check(database: Database) -> int:
    """输出项目自校验结果并返回对应退出码。"""

    problems = database.project_check()
    if not problems:
        print("项目自校验：ok")
        return 0
    print("项目自校验失败：")
    for problem in problems:
        print(f"- {problem}")
    return 2


def _print_scan_status(database: Database, scan_id: str | None) -> int:
    """输出指定扫描或全部扫描的稳定 JSON 状态。"""

    scans = [database.get_scan(scan_id)] if scan_id else database.iter_scans()
    payload = [dict(scan) for scan in scans if scan is not None]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload else 1


def _import_database(database: Database, source_path: Path, destination_path: Path) -> None:
    """从另一项目数据库复制全部内容，拒绝源与目标为同一文件。"""

    if destination_path.resolve() == source_path.resolve():
        raise ValueError("导入源数据库不能与目标数据库相同")
    with Database.open_existing(source_path) as source:
        source.connection.backup(database.connection)


def _scan_options(defaults: ScanConfig, args: argparse.Namespace) -> ScanConfig:
    """将命令行覆盖项合并到配置文件的安全默认值。"""

    hash_mode = getattr(args, "hash_mode", None)
    sample_budget = getattr(args, "sample_budget", None)
    sample_count = getattr(args, "sample_count", None)
    values = {
        "workers": args.workers if args.workers is not None else defaults.workers,
        "queue_size": args.queue_size if args.queue_size is not None else defaults.queue_size,
        "chunk_size": args.chunk_size if args.chunk_size is not None else defaults.chunk_size,
        "sha512": args.sha512 or defaults.sha512,
        "hash_mode": HashMode(hash_mode) if hash_mode else defaults.hash_mode,
        "sample_budget": sample_budget if sample_budget is not None else defaults.sample_budget,
        "sample_count": sample_count if sample_count is not None else defaults.sample_count,
        "follow_links": args.follow_links or defaults.follow_links,
    }
    return replace(defaults, **values)

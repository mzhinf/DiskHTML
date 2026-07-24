"""生成可用于 DiskHTML 压力测量的确定性文件集。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter


def _parser() -> argparse.ArgumentParser:
    """构建压力数据集生成参数。"""

    parser = argparse.ArgumentParser(description="DiskHTML 压力数据集生成器")
    parser.add_argument("output", type=Path, help="新建的数据集目录")
    parser.add_argument("--files", type=int, default=10_000, help="要创建的文件数")
    parser.add_argument("--size-bytes", type=int, default=0, help="每个文件的逻辑字节数")
    parser.add_argument(
        "--files-per-directory", type=int, default=1_000, help="每个子目录包含的文件数"
    )
    parser.add_argument("--progress-every", type=int, default=10_000, help="进度输出间隔")
    return parser


def _validate(args: argparse.Namespace) -> None:
    """拒绝会生成无效目录结构的参数。"""

    for name in ("files", "files_per_directory", "progress_every"):
        if getattr(args, name) < 1:
            raise ValueError(f"{name} 必须大于 0")
    if args.size_bytes < 0:
        raise ValueError("size_bytes 不能为负数")
    if args.output.exists():
        raise FileExistsError(f"数据集目录已存在：{args.output}")


def main(argv: list[str] | None = None) -> int:
    """生成数据集并写入描述本次条件的清单。"""

    args = _parser().parse_args(argv)
    _validate(args)
    output = args.output.expanduser()
    output.mkdir(parents=True)
    started = perf_counter()
    try:
        for index in range(args.files):
            directory = output / f"batch-{index // args.files_per_directory:06d}"
            directory.mkdir(exist_ok=True)
            path = directory / f"file-{index % args.files_per_directory:06d}.bin"
            with path.open("xb") as handle:
                if args.size_bytes:
                    handle.truncate(args.size_bytes)
            completed = index + 1
            if completed % args.progress_every == 0 or completed == args.files:
                elapsed = perf_counter() - started
                print(f"已创建 {completed}/{args.files} 个文件，耗时 {elapsed:.2f} 秒")

        manifest = {
            "format_version": 1,
            "files": args.files,
            "size_bytes_per_file": args.size_bytes,
            "files_per_directory": args.files_per_directory,
            "directories": (args.files + args.files_per_directory - 1) // args.files_per_directory,
            "elapsed_seconds": round(perf_counter() - started, 6),
        }
        (output / "dataset.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except BaseException:
        print(f"生成失败，已保留现场目录：{output}", file=sys.stderr)
        raise

    print(f"数据集清单：{output / 'dataset.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""为 Windows 图形界面发布包生成可追溯的 SHA256 清单。"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def _sha256(path: Path) -> str:
    """以有界读取计算单个文件的 SHA256。"""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def _package_size(package: Path) -> tuple[int, int]:
    """统计发布目录内的文件数与总字节数。"""

    files = tuple(item for item in package.rglob("*") if item.is_file())
    return len(files), sum(item.stat().st_size for item in files)


def _parser() -> argparse.ArgumentParser:
    """构建发布清单命令参数。"""

    parser = argparse.ArgumentParser(description="DiskHTML Windows 发布包清单生成器")
    parser.add_argument("package", type=Path, help="包含 DiskHTML.exe 的发布目录")
    parser.add_argument("output", type=Path, help="新建的 JSON 清单路径")
    parser.add_argument("--executable", default="DiskHTML.exe", help="发布可执行文件名")
    return parser


def main(argv: list[str] | None = None) -> int:
    """校验发布目录并生成独立的可复核清单。"""

    args = _parser().parse_args(argv)
    package = args.package.expanduser()
    output = args.output.expanduser()
    executable = package / args.executable
    if not package.is_dir():
        raise NotADirectoryError(f"发布目录不存在：{package}")
    if not executable.is_file():
        raise FileNotFoundError(f"发布可执行文件不存在：{executable}")
    if output.exists():
        raise FileExistsError(f"发布清单已存在：{output}")

    file_count, package_bytes = _package_size(package)
    manifest = {
        "format_version": 1,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "package_name": package.name,
        "package_file_count": file_count,
        "package_bytes": package_bytes,
        "executable": {
            "name": executable.name,
            "bytes": executable.stat().st_size,
            "sha256": _sha256(executable),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"发布清单：{output}")
    print(f"可执行文件 SHA256：{manifest['executable']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

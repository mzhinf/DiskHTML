"""解压 DiskHTML 发布 ZIP，并验证运行时、许可证和真实快照生成。"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

try:
    from project_metadata import read_project_version
    from release_licenses import ReleaseLicenseError, verify_license_bundle
except ModuleNotFoundError:
    from scripts.project_metadata import read_project_version
    from scripts.release_licenses import ReleaseLicenseError, verify_license_bundle


def _validate_archive_members(archive: zipfile.ZipFile) -> None:
    """在解压前拒绝绝对路径和父目录穿越条目。"""

    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"发布 ZIP 包含不安全路径：{member.filename}")


def _validate_runtime_layout(package: Path) -> None:
    """确认最终发布包包含 Tkinter 且完全不含 Qt 运行时。"""

    internal = package / "_internal"
    required_files = (
        internal / "python312.dll",
        internal / "_tkinter.pyd",
    )
    missing = [item.name for item in required_files if not item.is_file()]
    if not any(internal.glob("tcl*.dll")):
        missing.append("tcl*.dll")
    if not any(internal.glob("tk*.dll")):
        missing.append("tk*.dll")
    for directory in ("_tcl_data", "_tk_data"):
        if not (internal / directory).is_dir():
            missing.append(directory)
    if missing:
        raise RuntimeError("发布包缺少 Tkinter 运行时：" + ", ".join(missing))

    qt_paths = [
        item.relative_to(package).as_posix()
        for pattern in ("PySide6", "shiboken6", "Qt6*.dll")
        for item in internal.rglob(pattern)
    ]
    if qt_paths:
        raise RuntimeError("Tkinter 发布包仍包含 Qt 文件：" + ", ".join(sorted(qt_paths)))


def _validate_embedded_project_version(package: Path, expected_version: str) -> None:
    """确认冻结应用携带的项目元数据与构建版本一致。"""

    embedded_metadata = package / "_internal" / "pyproject.toml"
    if not embedded_metadata.is_file():
        raise RuntimeError("发布包缺少运行时版本元数据：_internal/pyproject.toml")
    if read_project_version(embedded_metadata.parent) != expected_version:
        raise RuntimeError("发布包内的产品版本与仓库 pyproject.toml 不一致")


def verify_release(archive_path: Path) -> None:
    """校验包结构，并在隔离目录运行解压后的 EXE。"""

    archive_path = archive_path.resolve()
    if not archive_path.is_file():
        raise FileNotFoundError(f"找不到发布 ZIP：{archive_path}")

    with tempfile.TemporaryDirectory(prefix="diskhtml-release-") as temporary:
        extracted = Path(temporary)
        with zipfile.ZipFile(archive_path) as archive:
            _validate_archive_members(archive)
            archive.extractall(extracted)

        package = extracted / "DiskHTML"
        executable = package / "DiskHTML.exe"
        if not executable.is_file():
            raise RuntimeError("发布 ZIP 根目录缺少 DiskHTML/DiskHTML.exe")

        _validate_runtime_layout(package)
        verify_license_bundle(package)

        subprocess.run([str(executable), "--version"], check=True, timeout=60)
        source = extracted / "样本目录"
        source.mkdir()
        (source / "中文.txt").write_text("DiskHTML release smoke test\n", encoding="utf-8")
        output = extracted / "snapshot.html"
        subprocess.run(
            [str(executable), "snapshot", str(source), str(output)],
            check=True,
            timeout=180,
        )

        database = output.with_suffix(".sqlite3")
        if not output.is_file() or not database.is_file():
            raise RuntimeError("解压后的 EXE 未同时生成 HTML 和 SQLite")
        html = output.read_text(encoding="utf-8")
        if "DiskHTML" not in html or "中文.txt" not in html:
            raise RuntimeError("生成的 HTML 缺少预期 UTF-8 快照数据")


def build_parser() -> argparse.ArgumentParser:
    """创建发布验证命令行解析器。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="需要验证的 DiskHTML-win-x64.zip")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """运行隔离发布验证并返回适合 CI 使用的状态码。"""

    args = build_parser().parse_args(argv)
    try:
        verify_release(args.archive)
    except (
        OSError,
        RuntimeError,
        ReleaseLicenseError,
        subprocess.SubprocessError,
        ValueError,
        zipfile.BadZipFile,
    ) as exc:
        print(f"发布验证失败：{exc}", file=sys.stderr)
        return 1
    print(f"发布验证通过：{args.archive.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

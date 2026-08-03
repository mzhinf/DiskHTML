"""使用 Python 构建并打包 Windows DiskHTML 应用，不依赖 PowerShell。"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Sequence
from pathlib import Path

try:
    from project_metadata import read_project_version, write_windows_version_resource
    from release_licenses import build_license_bundle
except ModuleNotFoundError:
    from scripts.project_metadata import read_project_version, write_windows_version_resource
    from scripts.release_licenses import build_license_bundle


def _remove_generated(path: Path, build_root: Path) -> None:
    """仅在目标位于项目构建目录内时删除已生成的文件。"""

    resolved = path.resolve(strict=False)
    resolved_root = build_root.resolve(strict=False)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"Refusing to remove a path outside build: {resolved}")
    if resolved.is_dir():
        shutil.rmtree(resolved)
    elif resolved.exists():
        resolved.unlink()


def _controlled_build_environment(python: Path) -> dict[str, str]:
    """将 PyInstaller 的 DLL 搜索范围限制到选定的 CPython 运行时。"""

    runtime_root = Path(sys.base_prefix).resolve()
    allowed_paths = (python.parent.resolve(), runtime_root, runtime_root / "DLLs")
    environment = os.environ.copy()
    system_root = Path(environment.get("SystemRoot", r"C:\Windows"))
    environment["PATH"] = os.pathsep.join(
        str(path)
        for path in (*allowed_paths, system_root / "System32", system_root)
        if path.is_dir()
    )
    return environment


def _write_release_archive(package: Path, archive: Path) -> None:
    """创建仅包含完整 DiskHTML 目录作为顶层条目的 ZIP。"""

    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for item in sorted(package.rglob("*")):
            if item.is_file():
                output.write(item, Path(package.name) / item.relative_to(package))


def build_windows(project_root: Path, *, clean: bool = False) -> tuple[Path, Path]:
    """构建 PyInstaller onedir 发布包并返回 EXE 与发布 ZIP 路径。"""

    root = project_root.resolve()
    python = root / ".venv" / "Scripts" / "python.exe"
    build_root = root / "build"
    dist = build_root / "dist"
    package = dist / "DiskHTML"
    executable = package / "DiskHTML.exe"
    internal = package / "_internal"
    assets = root / "src" / "diskhtml" / "assets"
    executable_icon = assets / "folder-tree.ico"
    legacy_single_file = dist / "DiskHTML.exe"
    release_archive = build_root / "release" / "DiskHTML-win-x64.zip"
    project_version = read_project_version(root)

    if not python.is_file():
        raise FileNotFoundError(f"Project virtual environment was not found: {python}")
    if clean:
        _remove_generated(build_root, build_root)

    for generated in (package, release_archive, legacy_single_file):
        _remove_generated(generated, build_root)

    version_resource = write_windows_version_resource(
        build_root / "DiskHTML-version-info.txt", project_version
    )
    command = [
        str(python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        "DiskHTML",
        "--icon",
        str(executable_icon),
        "--version-file",
        str(version_resource),
        "--add-data",
        f"{assets}{os.pathsep}diskhtml/assets",
        "--add-data",
        f"{root / 'pyproject.toml'}{os.pathsep}.",
        "--paths",
        str(root / "src"),
        "--distpath",
        str(dist),
        "--workpath",
        str(build_root / "work"),
        "--specpath",
        str(build_root),
        str(root / "scripts" / "gui_entry.py"),
    ]
    subprocess.run(command, cwd=root, check=True, env=_controlled_build_environment(python))

    if not executable.is_file():
        raise RuntimeError(f"Build completed without the executable: {executable}")
    if not internal.is_dir():
        raise RuntimeError(f"Build completed without the runtime directory: {internal}")

    build_license_bundle(package, root, build_root / "release" / "license-audit.json")

    _write_release_archive(package, release_archive)
    if not release_archive.is_file():
        raise RuntimeError(f"Release archive was not created: {release_archive}")
    return executable, release_archive


def build_parser() -> argparse.ArgumentParser:
    """创建便携式 Windows 构建命令行解析器。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true", help="先删除构建目录")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """从包含该脚本的仓库执行 Windows 构建。"""

    args = build_parser().parse_args(argv)
    try:
        executable, archive = build_windows(Path(__file__).resolve().parents[1], clean=args.clean)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1
    print(f"DiskHTML EXE: {executable}")
    print(f"Release ZIP: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

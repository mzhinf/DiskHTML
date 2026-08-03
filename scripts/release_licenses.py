"""从最终 Windows 发布目录生成并校验第三方许可证材料。"""

from __future__ import annotations

import argparse
import ctypes
import importlib.metadata
import json
import re
import shutil
import sqlite3
import ssl
import sys
from collections.abc import Iterable
from ctypes import wintypes
from dataclasses import asdict, dataclass
from pathlib import Path

REVIEWED_RUNTIME_BUILD = "20260414"
REVIEWED_SOURCE_ROOT = (
    Path(__file__).resolve().parents[1] / "third_party" / "license_sources" / "upstream"
)


class ReleaseLicenseError(RuntimeError):
    """发布包无法生成完整许可证材料时抛出。"""


@dataclass(frozen=True)
class ReleaseComponent:
    """从最终 onedir 发布包文件中识别出的第三方组件。"""

    category: str
    name: str
    version: str
    license_type: str
    copyright: str
    website: str
    evidence: tuple[str, ...]
    license_source: Path | None = None
    license_filename: str | None = None
    review_reason: str | None = None

    @property
    def is_resolved(self) -> bool:
        """返回组件是否具有已核验许可证来源和完整声明字段。"""

        return (
            self.license_source is not None
            and self.license_source.is_file()
            and self.license_filename is not None
            and self.review_reason is None
        )


@dataclass(frozen=True)
class _RuntimeLibraryDefinition:
    """描述与固定 Python 运行时一同发布的原生组件许可证规则。"""

    name: str
    version: str
    license_type: str
    copyright_text: str
    website: str
    patterns: tuple[str, ...]
    source_name: str
    output_name: str


class _VsFixedFileInfo(ctypes.Structure):
    """Windows PE 版本资源根结构。"""

    _fields_ = [
        ("signature", wintypes.DWORD),
        ("structure_version", wintypes.DWORD),
        ("file_version_ms", wintypes.DWORD),
        ("file_version_ls", wintypes.DWORD),
        ("product_version_ms", wintypes.DWORD),
        ("product_version_ls", wintypes.DWORD),
        ("file_flags_mask", wintypes.DWORD),
        ("file_flags", wintypes.DWORD),
        ("file_os", wintypes.DWORD),
        ("file_type", wintypes.DWORD),
        ("file_subtype", wintypes.DWORD),
        ("file_date_ms", wintypes.DWORD),
        ("file_date_ls", wintypes.DWORD),
    ]


def _matching_files(package: Path, patterns: Iterable[str]) -> tuple[Path, ...]:
    """返回一个或多个模式命中的最终发布文件。"""

    matches: set[Path] = set()
    for pattern in patterns:
        matches.update(item for item in package.glob(pattern) if item.is_file())
    return tuple(sorted(matches))


def _evidence(package: Path, patterns: Iterable[str]) -> tuple[str, ...]:
    """把最终发布文件格式化为稳定的包内相对路径证据。"""

    return tuple(
        item.relative_to(package).as_posix() for item in _matching_files(package, patterns)
    )


def _distribution_license(distribution: str, filename: str) -> Path | None:
    """从实际构建依赖安装元数据中定位其自带许可证。"""

    try:
        files = importlib.metadata.files(distribution) or ()
        root = Path(importlib.metadata.distribution(distribution).locate_file("."))
    except importlib.metadata.PackageNotFoundError:
        return None
    for item in files:
        if item.name == filename:
            candidate = root / item
            if candidate.is_file():
                return candidate
    return None


def _runtime_license() -> Path | None:
    """定位执行构建的 CPython 发行版许可证。"""

    candidate = Path(sys.base_prefix) / "LICENSE.txt"
    return candidate if candidate.is_file() else None


def _runtime_build_id() -> str | None:
    """读取 uv Python 发行版的不可变构建编号。"""

    candidate = Path(sys.base_prefix) / "BUILD"
    if not candidate.is_file():
        return None
    value = candidate.read_text(encoding="utf-8").strip()
    return value or None


def _reviewed_source(filename: str) -> Path | None:
    """返回仓库内经过来源与哈希登记的许可证原文。"""

    candidate = REVIEWED_SOURCE_ROOT / filename
    return candidate if candidate.is_file() else None


def _project_license(project_root: Path) -> Path:
    """返回维护者提供的项目许可证，不推测或修改内容。"""

    candidates = tuple(
        path
        for path in project_root.iterdir()
        if path.is_file()
        and path.name.casefold() in {"license", "license.txt", "copying", "copying.txt"}
    )
    if not candidates:
        raise ReleaseLicenseError("仓库根目录缺少维护者确认的 LICENSE 或 LICENSE.txt。")
    if len(candidates) != 1:
        names = ", ".join(path.name for path in candidates)
        raise ReleaseLicenseError(f"项目许可证不唯一，请只保留一个根许可证文件：{names}")
    return candidates[0]


def _file_version(path: Path) -> str | None:
    """读取最终 Windows PE 文件的四段版本号。"""

    if sys.platform != "win32" or not path.is_file():
        return None
    version_api = ctypes.windll.version
    size = version_api.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return None
    buffer = ctypes.create_string_buffer(size)
    if not version_api.GetFileVersionInfoW(str(path), 0, size, buffer):
        return None
    pointer = ctypes.c_void_p()
    length = wintypes.UINT()
    if not version_api.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
        return None
    if length.value < ctypes.sizeof(_VsFixedFileInfo):
        return None
    info = ctypes.cast(pointer, ctypes.POINTER(_VsFixedFileInfo)).contents
    if info.signature != 0xFEEF04BD:
        return None
    parts = (
        info.file_version_ms >> 16,
        info.file_version_ms & 0xFFFF,
        info.file_version_ls >> 16,
        info.file_version_ls & 0xFFFF,
    )
    while len(parts) > 3 and parts[-1] == 0:
        parts = parts[:-1]
    return ".".join(str(part) for part in parts)


def _first_file_version(package: Path, patterns: Iterable[str]) -> str | None:
    """从命中的第一个 PE 文件读取版本。"""

    files = _matching_files(package, patterns)
    return _file_version(files[0]) if files else None


def _tcl_tk_license(package: Path) -> Path | None:
    """优先使用最终发布包中 Tk 自带的一级许可证来源。"""

    candidates = (
        package / "_internal" / "_tk_data" / "license.terms",
        package / "_internal" / "_tcl_data" / "license.terms",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _tcl_tk_version(package: Path) -> str | None:
    """从最终包的 init.tcl 读取 Tcl/Tk 语义版本。"""

    init_script = package / "_internal" / "_tcl_data" / "init.tcl"
    if not init_script.is_file():
        return None
    match = re.search(
        r"package\s+require\s+-exact\s+Tcl\s+([0-9.]+)",
        init_script.read_text(encoding="utf-8"),
    )
    return match.group(1) if match else None


def _runtime_component(
    package: Path,
    *,
    category: str,
    name: str,
    version: str,
    license_type: str,
    copyright_text: str,
    website: str,
    patterns: tuple[str, ...],
    source_name: str,
    output_name: str,
) -> ReleaseComponent | None:
    """按最终文件证据创建与当前不可变 Python 发行版绑定的组件。"""

    evidence = _evidence(package, patterns)
    if not evidence:
        return None
    build_id = _runtime_build_id()
    source = _reviewed_source(source_name) if build_id == REVIEWED_RUNTIME_BUILD else None
    reason = None
    if build_id != REVIEWED_RUNTIME_BUILD:
        reason = f"当前构建运行时编号为 {build_id or '未知'}，尚未核对其 {name} 版本和许可证来源。"
    elif source is None:
        reason = f"缺少已登记许可证来源：{source_name}"
    return ReleaseComponent(
        category,
        name,
        version,
        license_type,
        copyright_text,
        website,
        evidence,
        source,
        output_name,
        reason,
    )


def discover_components(package: Path) -> tuple[ReleaseComponent, ...]:
    """只根据最终发布目录实际存在的文件识别第三方组件。"""

    package = package.resolve()
    components = [
        component
        for component in (
            _discover_python_component(package),
            _discover_pyinstaller_component(package),
            _discover_tcl_tk_component(package),
            _discover_unexpected_qt_component(package),
            _discover_lucide_component(package),
        )
        if component is not None
    ]
    components.extend(_discover_runtime_library_components(package))
    components.extend(
        component
        for component in (
            _discover_openssl_component(package),
            _discover_sqlite_component(package),
            _discover_visual_cpp_component(package),
        )
        if component is not None
    )
    return tuple(components)


def _discover_python_component(package: Path) -> ReleaseComponent | None:
    """识别最终包中的 CPython 运行时与标准库。"""

    evidence = _evidence(package, ("_internal/python*.dll", "_internal/base_library.zip"))
    if not evidence:
        return None
    version = ".".join(map(str, sys.version_info[:3]))
    return ReleaseComponent(
        "Python Runtime & Standard Libraries",
        "Python",
        version,
        "Python Software Foundation License",
        "Copyright (c) 2001-2026 Python Software Foundation.",
        "https://www.python.org/",
        evidence,
        _runtime_license(),
        f"Python-{version}.txt",
    )


def _discover_pyinstaller_component(package: Path) -> ReleaseComponent | None:
    """在最终可执行文件存在时声明 PyInstaller 启动器和运行钩子。"""

    if not (package / "DiskHTML.exe").is_file():
        return None
    version = importlib.metadata.version("pyinstaller")
    return ReleaseComponent(
        "Python Packages",
        "PyInstaller Bootloader and Runtime Hooks",
        version,
        "GNU General Public License v2 or later with a bootloader exception",
        "Copyright (c) 2010-2026 PyInstaller Development Team.",
        "https://pyinstaller.org/",
        ("DiskHTML.exe (embedded bootloader)",),
        _distribution_license("pyinstaller", "COPYING.txt"),
        f"PyInstaller-{version}.txt",
    )


def _discover_tcl_tk_component(package: Path) -> ReleaseComponent | None:
    """识别 Tkinter 随最终发布目录携带的 Tcl/Tk 运行时。"""

    evidence = _evidence(
        package,
        (
            "_internal/_tkinter.pyd",
            "_internal/tcl*.dll",
            "_internal/tk*.dll",
            "_internal/_tcl_data/**/*",
            "_internal/_tk_data/**/*",
        ),
    )
    if not evidence:
        return None
    version = _tcl_tk_version(package)
    source = _tcl_tk_license(package)
    return ReleaseComponent(
        "GUI Runtime",
        "Tcl/Tk Runtime",
        version,
        "Tcl/Tk License (BSD-style)",
        "Copyright held by the Regents of the University of California, Sun Microsystems, Scriptics, ActiveState, Apple, and other contributors.",
        "https://www.tcl-lang.org/",
        evidence,
        source,
        f"Tcl-Tk-{version}.license.terms",
        None if source else "最终发布包缺少 Tcl/Tk 自带的 license.terms。",
    )


def _discover_unexpected_qt_component(package: Path) -> ReleaseComponent | None:
    """将任何残留 Qt 运行时显式标记为不可发布组件。"""

    evidence = _evidence(package, ("_internal/PySide6/**/*", "_internal/shiboken6/**/*"))
    if not evidence:
        return None
    return ReleaseComponent(
        "GUI Runtime",
        "Unexpected Qt Runtime",
        "不应存在",
        "未选择",
        "不适用。",
        "https://www.qt.io/licensing/",
        evidence,
        review_reason="Tkinter 发布包仍包含 PySide6、shiboken6 或 Qt 文件，必须清理后重新构建。",
    )


def _discover_lucide_component(package: Path) -> ReleaseComponent | None:
    """识别实际随应用发布的 Lucide SVG、PNG 与 ICO 素材。"""

    evidence = _evidence(
        package,
        (
            "_internal/diskhtml/assets/*.svg",
            "_internal/diskhtml/assets/*.png",
            "_internal/diskhtml/assets/*.ico",
        ),
    )
    if not evidence:
        return None
    source = _reviewed_source("Lucide-1.27.0.txt")
    return ReleaseComponent(
        "Embedded Assets",
        "Lucide Icons",
        "1.27.0",
        "ISC License; selected Feather-derived icons under the MIT License",
        "Copyright (c) 2026 Lucide Icons and Contributors; Feather portions Copyright (c) 2013-present Cole Bemis.",
        "https://lucide.dev/",
        evidence,
        source,
        "Lucide-1.27.0.txt",
        None if source else "缺少 Lucide 1.27.0 官方完整许可证。",
    )


_NATIVE_RUNTIME_COMPONENTS = (
    _RuntimeLibraryDefinition(
        "bzip2",
        "1.0.8",
        "bzip2 License",
        "Copyright (c) 1996-2019 Julian Seward.",
        "https://sourceware.org/bzip2/",
        ("_internal/_bz2.pyd",),
        "python-build-standalone-20260414-bzip2.txt",
        "bzip2-1.0.8.txt",
    ),
    _RuntimeLibraryDefinition(
        "Expat",
        "2.6.3",
        "MIT License",
        "Copyright (c) 1998-2000 Thai Open Source Software Center Ltd and Clark Cooper; subsequent contributors.",
        "https://libexpat.github.io/",
        ("_internal/pyexpat.pyd",),
        "python-build-standalone-20260414-expat.txt",
        "Expat-2.6.3.txt",
    ),
    _RuntimeLibraryDefinition(
        "libffi",
        "3.4.6",
        "MIT License",
        "Copyright (c) 1996-2024 Anthony Green, Red Hat, Inc. and others.",
        "https://github.com/libffi/libffi",
        ("_internal/libffi-*.dll", "_internal/_ctypes.pyd"),
        "libffi-python-build-standalone-20260414.txt",
        "libffi-3.4.6.txt",
    ),
    _RuntimeLibraryDefinition(
        "XZ Utils / liblzma",
        "5.8.1",
        "0BSD License and public-domain notices",
        "Copyright held by the XZ Utils authors and contributors as listed in the license text.",
        "https://tukaani.org/xz/",
        ("_internal/_lzma.pyd", "_internal/liblzma*.dll"),
        "python-build-standalone-20260414-liblzma.txt",
        "XZ-Utils-5.8.1.txt",
    ),
    _RuntimeLibraryDefinition(
        "mpdecimal",
        "4.0.0",
        "BSD-2-Clause License",
        "Copyright (c) 2008-2024 Stefan Krah. All rights reserved.",
        "https://www.bytereef.org/mpdecimal/",
        ("_internal/_decimal.pyd",),
        "python-build-standalone-20260414-mpdecimal.txt",
        "mpdecimal-4.0.0.txt",
    ),
    _RuntimeLibraryDefinition(
        "zlib",
        "1.3.1",
        "zlib License",
        "Copyright (c) 1995-2024 Jean-loup Gailly and Mark Adler.",
        "https://zlib.net/",
        ("_internal/zlib*.dll", "_internal/zlib.pyd", "_internal/python3??.dll"),
        "python-build-standalone-20260414-zlib.txt",
        "zlib-1.3.1.txt",
    ),
)


def _discover_runtime_library_components(package: Path) -> list[ReleaseComponent]:
    """按固定声明顺序识别和返回 Python 运行时附带的原生库。"""

    return [
        component
        for definition in _NATIVE_RUNTIME_COMPONENTS
        if (
            component := _runtime_component(
                package,
                category="Native Libraries",
                name=definition.name,
                version=definition.version,
                license_type=definition.license_type,
                copyright_text=definition.copyright_text,
                website=definition.website,
                patterns=definition.patterns,
                source_name=definition.source_name,
                output_name=definition.output_name,
            )
        )
        is not None
    ]


def _discover_openssl_component(package: Path) -> ReleaseComponent | None:
    """识别最终目录中的 OpenSSL 动态库并固定到同版本许可证。"""

    evidence = _evidence(package, ("_internal/libcrypto-*.dll", "_internal/libssl-*.dll"))
    if not evidence:
        return None
    detected = _first_file_version(package, ("_internal/libcrypto-*.dll",))
    version = detected or re.sub(r"^OpenSSL\s+", "", ssl.OPENSSL_VERSION).split()[0]
    source = _reviewed_source("OpenSSL-3.5.6.txt") if version == "3.5.6" else None
    return ReleaseComponent(
        "Native Libraries",
        "OpenSSL",
        version,
        "Apache License 2.0",
        "Copyright (c) 1998-2026 The OpenSSL Project Authors.",
        "https://www.openssl.org/",
        evidence,
        source,
        f"OpenSSL-{version}.txt",
        None if source else f"OpenSSL {version} 尚无同版本核验许可证。",
    )


def _discover_sqlite_component(package: Path) -> ReleaseComponent | None:
    """识别最终目录中的 SQLite 组件并固定到同版本许可证。"""

    evidence = _evidence(package, ("_internal/sqlite3.dll", "_internal/_sqlite3.pyd"))
    if not evidence:
        return None
    detected = _first_file_version(package, ("_internal/sqlite3.dll",))
    version = detected or sqlite3.sqlite_version
    source = _reviewed_source("SQLite-3.50.4-Public-Domain.txt") if version == "3.50.4" else None
    return ReleaseComponent(
        "Native Libraries",
        "SQLite",
        version,
        "Public Domain",
        "The SQLite authors have dedicated the code to the public domain.",
        "https://www.sqlite.org/",
        evidence,
        source,
        f"SQLite-{version}.txt",
        None if source else f"SQLite {version} 尚无同版本核验许可证。",
    )


def _discover_visual_cpp_component(package: Path) -> ReleaseComponent | None:
    """识别最终目录中的 Microsoft Visual C++ Runtime。"""

    evidence = _evidence(
        package,
        ("_internal/VCRUNTIME*.dll", "_internal/ucrtbase.dll", "_internal/api-ms-win-*.dll"),
    )
    if not evidence:
        return None
    version = _first_file_version(package, ("_internal/VCRUNTIME*.dll",))
    source = _reviewed_source("Microsoft-Visual-Cpp-Runtime-2015-2022.txt")
    reason = None
    if version is None:
        reason = "无法从最终 VCRUNTIME DLL 读取版本号。"
    elif source is None:
        reason = "缺少 Microsoft Visual C++ Runtime 2015-2022 官方许可证。"
    return ReleaseComponent(
        "Native Libraries",
        "Microsoft Visual C++ Runtime",
        version or "未知",
        "Microsoft Software License Terms",
        "Copyright (c) Microsoft Corporation. All rights reserved.",
        "https://visualstudio.microsoft.com/license-terms/vs2022-cruntime/",
        evidence,
        source,
        "Microsoft-Visual-Cpp-Runtime-2015-2022.txt",
        reason,
    )


def _write_audit(
    report_path: Path, components: tuple[ReleaseComponent, ...], error: str | None
) -> None:
    """在发布输出旁写入机器可读审计记录，不放入 ZIP。"""

    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format_version": 1,
        "status": "passed" if error is None else "manual-review-required",
        "error": error,
        "components": [
            {
                **asdict(component),
                "license_source": str(component.license_source)
                if component.license_source
                else None,
                "resolved": component.is_resolved,
            }
            for component in components
        ],
    }
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _notice_text(components: tuple[ReleaseComponent, ...]) -> str:
    """生成要求为英文纯文本的第三方声明文件。"""

    lines = [
        "=" * 72,
        "THIRD-PARTY SOFTWARE NOTICES AND INFORMATION",
        "=" * 72,
        "",
        "This application incorporates third-party open-source materials and",
        "components. The original software and raw source code remain the property",
        "of their respective owners.",
        "",
        "The full license texts for these third-party components can be found in",
        'the "licenses/" directory included with this distribution.',
        "",
    ]
    categories: list[str] = []
    for component in components:
        if component.category not in categories:
            categories.append(component.category)
    for number, category in enumerate(categories, start=1):
        lines.extend(("=" * 72, f"{number}. {category}", "=" * 72))
        for component in (item for item in components if item.category == category):
            lines.extend(
                (
                    f"Component Name:  {component.name}",
                    f"Version:         {component.version}",
                    f"License Type:    {component.license_type}",
                    f"Copyright:       {component.copyright}",
                    f"License File:    licenses/{component.license_filename}",
                    f"Website:         {component.website}",
                    "",
                )
            )
    return "\n".join(lines)


def build_license_bundle(package: Path, project_root: Path, audit_path: Path) -> None:
    """生成完整许可证目录；发现未核验组件时在创建 ZIP 前失败。"""

    package = package.resolve()
    components = discover_components(package)
    try:
        project_license = _project_license(project_root.resolve())
        unresolved = tuple(component for component in components if not component.is_resolved)
        if unresolved:
            detail = "; ".join(f"{item.name}: {item.review_reason}" for item in unresolved)
            raise ReleaseLicenseError(f"发布许可证核验未完成：{detail}")
    except ReleaseLicenseError as exc:
        _write_audit(audit_path, components, str(exc))
        raise

    licenses = package / "licenses"
    temporary = package / ".licenses-staging"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        shutil.copyfile(project_license, temporary / "LICENSE.txt")
        license_directory = temporary / "licenses"
        license_directory.mkdir()
        for component in components:
            assert component.license_source is not None and component.license_filename is not None
            shutil.copyfile(
                component.license_source, license_directory / component.license_filename
            )
        (temporary / "THIRD-PARTY-NOTICES.txt").write_text(
            _notice_text(components), encoding="utf-8"
        )
        if licenses.exists():
            shutil.rmtree(licenses)
        for filename in ("LICENSE.txt", "THIRD-PARTY-NOTICES.txt"):
            destination = package / filename
            if destination.exists():
                destination.unlink()
            (temporary / filename).replace(destination)
        (temporary / "licenses").replace(licenses)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    _write_audit(audit_path, components, None)


def verify_license_bundle(package: Path) -> None:
    """解压后反向校验许可证目录、声明引用和实际组件清单。"""

    package = package.resolve()
    required = (package / "LICENSE.txt", package / "THIRD-PARTY-NOTICES.txt", package / "licenses")
    missing = [item.name for item in required if not item.exists()]
    if missing:
        raise ReleaseLicenseError(f"发布许可证目录不完整：{', '.join(missing)}")
    notice = (package / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
    declared_names: set[str] = set()
    declared_files: set[str] = set()
    for line in notice.splitlines():
        if line.startswith("Component Name:"):
            declared_names.add(line.split(":", 1)[1].strip())
        if line.startswith("License File:"):
            relative = line.split(":", 1)[1].strip().replace("/", "\\")
            candidate = package / relative
            if not candidate.is_file():
                raise ReleaseLicenseError(f"声明引用了不存在的许可证文件：{relative}")
            declared_files.add(Path(relative).name)
    discovered = discover_components(package)
    discovered_names = {component.name for component in discovered}
    if declared_names != discovered_names:
        missing_names = sorted(discovered_names - declared_names)
        extra_names = sorted(declared_names - discovered_names)
        raise ReleaseLicenseError(
            f"声明清单与解压后的实际组件不一致：缺少={missing_names}，多余={extra_names}"
        )
    actual_files = {item.name for item in (package / "licenses").iterdir() if item.is_file()}
    if actual_files != declared_files:
        raise ReleaseLicenseError(
            f"licenses 目录与声明引用不一致：实际={sorted(actual_files)}，声明={sorted(declared_files)}"
        )
    unresolved = [component.name for component in discovered if not component.is_resolved]
    if unresolved:
        raise ReleaseLicenseError("解压包仍有未核验组件：" + ", ".join(unresolved))


def _parser() -> argparse.ArgumentParser:
    """创建构建和手工审计共用的命令行解析器。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="包含 DiskHTML.exe 的最终 onedir 发布目录")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--audit", type=Path, required=True, help="发布目录外的 JSON 审计输出")
    return parser


def main() -> int:
    """执行许可证生成并返回适合构建脚本使用的状态码。"""

    args = _parser().parse_args()
    try:
        build_license_bundle(args.package, args.project_root, args.audit)
    except (OSError, ReleaseLicenseError, importlib.metadata.PackageNotFoundError) as exc:
        print(f"发布许可证生成失败：{exc}", file=sys.stderr)
        return 1
    print(f"发布许可证材料已生成：{args.package}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

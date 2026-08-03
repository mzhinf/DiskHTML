"""读取项目元数据并生成 Windows 发布版本资源。"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


def read_project_version(project_root: Path) -> str:
    """从项目唯一版本源 pyproject.toml 读取产品版本。"""

    metadata_path = project_root / "pyproject.toml"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"找不到项目元数据：{metadata_path}")
    with metadata_path.open("rb") as handle:
        project = tomllib.load(handle).get("project", {})
    version = project.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("pyproject.toml 缺少有效的 project.version")
    return version


def windows_version_parts(project_version: str) -> tuple[int, int, int, int]:
    """将稳定的三段产品版本转换为 Windows 四段文件版本。"""

    match = re.fullmatch(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?", project_version)
    if match is None:
        raise ValueError(f"Windows 发布版本必须是最多四段数字：{project_version}")
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def write_windows_version_resource(destination: Path, project_version: str) -> Path:
    """创建供 PyInstaller 写入 EXE 属性的版本资源文件。"""

    file_version = windows_version_parts(project_version)
    numeric_version = ", ".join(str(part) for part in file_version)
    resource = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({numeric_version}),
    prodvers=({numeric_version}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'DiskHTML'),
          StringStruct('FileDescription', 'DiskHTML HTML Snapshot Generator'),
          StringStruct('FileVersion', '{project_version}'),
          StringStruct('InternalName', 'DiskHTML'),
          StringStruct('OriginalFilename', 'DiskHTML.exe'),
          StringStruct('ProductName', 'DiskHTML'),
          StringStruct('ProductVersion', '{project_version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(resource, encoding="utf-8")
    return destination

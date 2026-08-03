"""从唯一的项目元数据读取 DiskHTML 产品版本。"""

from __future__ import annotations

import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

_DISTRIBUTION_NAME = "diskhtml"


def _project_metadata_paths() -> tuple[Path, ...]:
    """返回源码与冻结应用可能携带的项目元数据路径。"""

    module_path = Path(__file__).resolve()
    frozen_root = Path(getattr(sys, "_MEIPASS", module_path.parent))
    return (
        module_path.parents[2] / "pyproject.toml",
        module_path.parents[1] / "pyproject.toml",
        frozen_root / "pyproject.toml",
    )


def _version_from_project_metadata() -> str | None:
    """读取可用的 pyproject.toml 中的产品版本。"""

    for metadata_path in _project_metadata_paths():
        if not metadata_path.is_file():
            continue
        with metadata_path.open("rb") as handle:
            project = tomllib.load(handle).get("project", {})
        project_version = project.get("version")
        if isinstance(project_version, str) and project_version:
            return project_version
    return None


def get_version() -> str:
    """获取当前发行版本；源码与冻结应用优先读取唯一项目元数据。"""

    project_version = _version_from_project_metadata()
    if project_version is not None:
        return project_version
    try:
        return version(_DISTRIBUTION_NAME)
    except PackageNotFoundError as exc:
        raise RuntimeError("无法读取 DiskHTML 产品版本") from exc


__version__ = get_version()

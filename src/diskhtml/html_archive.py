"""单文件 HTML 快照与快照比较服务。"""

from __future__ import annotations

import html
import json
import os
import tempfile
import time
from collections.abc import Callable, Iterator
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any

from .archive_ui import document_footer as _ui_document_footer
from .archive_ui import page_header as _ui_page_header
from .archive_ui import tree_document as _ui_tree_document
from .compare import _iter_entries
from .config import ScanConfig
from .database import Database
from .models import CompareStatus, ScanProgress
from .scanner import ScanController, Scanner
from .util import utc_now

_ARCHIVE_FORMAT_VERSION = 1
_ARCHIVE_DATA_ID = "diskhtml-archive-data"
_RENDER_LIMIT = 500


def create_html_snapshot(
    source: Path | str,
    output_path: Path | str,
    options: ScanConfig | None = None,
    progress_callback: Callable[[ScanProgress], None] | None = None,
    controller: ScanController | None = None,
) -> Path:
    """扫描源路径并生成单个、可离线打开的可视化 HTML 快照。"""

    destination = _prepare_destination(output_path)
    database_path = _prepare_sqlite_destination(destination)
    try:
        with Database(database_path) as database:
            scan_id = Scanner(database, progress_callback).start(
                Path(source), options or ScanConfig(), controller
            )
            payload = _scan_payload(database, scan_id)
            _write_archive(destination, payload, _scan_document(payload))
    except BaseException:
        if not destination.exists():
            _remove_sqlite_artifacts(database_path)
        raise
    return destination


def render_html_snapshot_from_sqlite(database_path: Path | str, output_path: Path | str) -> Path:
    """从已保存的 SQLite 快照索引重新生成当前版本的 HTML 页面。"""

    destination = _prepare_destination(output_path)
    with Database.open_existing(database_path) as database:
        latest = database.latest_scan()
        if latest is None:
            raise ValueError("SQLite 快照中没有可用于生成 HTML 的已完成扫描")
        payload = _scan_payload(database, str(latest["id"]))
        _write_archive(destination, payload, _scan_document(payload))
    return destination


def compare_html_archives(
    left_path: Path | str, right_path: Path | str, output_path: Path | str
) -> Path:
    """\u517c\u5bb9\u6bd4\u8f83\u4e24\u4e2a HTML \u5feb\u7167\u5feb\u7167\uff0c\u5e76\u751f\u6210\u5355\u6587\u4ef6 HTML \u62a5\u544a\u3002"""
    destination = _prepare_destination(output_path)
    left = read_html_snapshot(left_path)
    right = read_html_snapshot(right_path)
    payload = _compare_payload(
        left,
        right,
        _snapshot_identity(left, left_path),
        _snapshot_identity(right, right_path),
    )
    _write_archive(destination, payload, _compare_document(payload))
    return destination


def compare_html_directory_to_source(
    archive_path: Path | str,
    archived_directory: str,
    source: Path | str,
    output_path: Path | str,
    options: ScanConfig | None = None,
    progress_callback: Callable[[ScanProgress], None] | None = None,
    controller: ScanController | None = None,
) -> Path:
    """\u5c06 HTML \u5feb\u7167\u4e2d\u9009\u5b9a\u76ee\u5f55\u4e0e\u672c\u673a\u76ee\u5f55\u6bd4\u8f83\uff0c\u5e76\u751f\u6210\u53ef\u89c6\u5316 HTML \u62a5\u544a\u3002"""
    destination = _prepare_destination(output_path)
    archive = read_html_snapshot(archive_path)
    directory = _normalize_directory(archived_directory)
    left = _selected_directory_payload(archive, directory)
    with tempfile.TemporaryDirectory(prefix="diskhtml-") as temporary_directory:
        database_path = Path(temporary_directory) / "transient-index.sqlite3"
        with Database(database_path) as database:
            scan_id = Scanner(database, progress_callback).start(
                Path(source), options or ScanConfig(), controller
            )
            right = _scan_payload(database, scan_id)
    left_identity = _snapshot_identity(archive, archive_path)
    left_identity["selected_directory"] = directory or "根目录"
    right_identity = _snapshot_identity(right, source)
    right_identity["selected_directory"] = "本机目录"
    payload = _compare_payload(left, right, left_identity, right_identity)
    _write_archive(destination, payload, _compare_document(payload))
    return destination


def html_snapshot_directories(path: Path | str) -> tuple[str, ...]:
    """返回 HTML 快照内可供用户选择的目录，根目录以空字符串表示。"""

    return _directories_from_payload(read_html_snapshot(path))


def _compare_payload(
    left: dict[str, Any],
    right: dict[str, Any],
    left_identity: dict[str, Any],
    right_identity: dict[str, Any],
) -> dict[str, Any]:
    """归并两侧文件清单并构建可写入比较报告的数据。"""

    entries = list(_iter_entries(_ordered_files(left), _ordered_files(right)))
    statistics = {status.value: 0 for status in CompareStatus}
    for entry in entries:
        statistics[str(entry["status"])] += 1
    return {
        "format_version": _ARCHIVE_FORMAT_VERSION,
        "kind": "compare",
        "generated_at": utc_now(),
        "left": left_identity,
        "right": right_identity,
        "statistics": statistics,
        "directories": _merge_directories(left, right),
        "entries": entries,
    }


def _merge_directories(left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, Any]]:
    """合并两侧目录元数据，右侧优先以展示本机当前时间。"""

    merged: dict[str, dict[str, Any]] = {}
    for payload in (left, right):
        for row in payload.get("directories", []):
            if not isinstance(row, dict):
                continue
            relative_path = str(row.get("relative_path") or "")
            merged[relative_path.casefold()] = {**row, "relative_path": relative_path}
    merged.setdefault("", {"relative_path": "", "path_key": ""})
    return sorted(merged.values(), key=lambda row: str(row["relative_path"]).casefold())


def _selected_directory_payload(payload: dict[str, Any], directory: str) -> dict[str, Any]:
    """从快照中截取指定目录，并将其重定根以与本机目录对齐。"""

    if directory not in _directories_from_payload(payload):
        raise ValueError(f"快照中不存在所选目录：{directory or '根目录'}")
    prefix = f"{directory}/" if directory else ""
    selected: list[dict[str, Any]] = []
    for row in payload["files"]:
        relative_path = str(row["relative_path"])
        if prefix and not relative_path.casefold().startswith(prefix.casefold()):
            continue
        item = dict(row)
        item["relative_path"] = relative_path[len(prefix) :]
        item["path_key"] = item["relative_path"].casefold()
        selected.append(item)
    selected_directories: list[dict[str, Any]] = []
    for row in payload.get("directories", []):
        if not isinstance(row, dict):
            continue
        relative_path = str(row.get("relative_path") or "")
        if prefix and relative_path and not relative_path.casefold().startswith(prefix.casefold()):
            continue
        item = dict(row)
        item["relative_path"] = relative_path[len(prefix) :] if prefix else relative_path
        item["path_key"] = item["relative_path"].casefold()
        selected_directories.append(item)
    return {**payload, "directories": selected_directories, "files": selected}


def _directories_from_payload(payload: dict[str, Any]) -> tuple[str, ...]:
    """从已解析的快照数据推导可选择目录，供内部选择逻辑复用。"""

    return html_snapshot_directories_from_rows(payload)


def html_snapshot_directories_from_rows(payload: dict[str, Any]) -> tuple[str, ...]:
    """基于快照记录产生目录集合，兼容早期不含 directories 的快照。"""

    directories = {""}
    for row in payload.get("directories", []):
        if isinstance(row, dict) and isinstance(row.get("relative_path"), str):
            directories.add(_normalize_directory(row["relative_path"]))
    for row in payload["files"]:
        if not isinstance(row, dict) or not isinstance(row.get("relative_path"), str):
            continue
        parts = PurePosixPath(row["relative_path"]).parts[:-1]
        for index in range(1, len(parts) + 1):
            directories.add("/".join(parts[:index]))
    return tuple(sorted(directories, key=str.casefold))


def _normalize_directory(directory: str) -> str:
    """规范化用户从 HTML 文件树选择的相对目录。"""

    normalized = directory.replace("\\", "/").strip("/")
    if normalized in {"", "."}:
        return ""
    if normalized.startswith("../") or "/../" in normalized:
        raise ValueError("快照目录不能包含上级路径")
    return normalized


def read_html_snapshot(path: Path | str) -> dict[str, Any]:
    """读取并校验 DiskHTML 单文件快照中的嵌入数据。"""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"找不到 HTML 快照：{source}")
    parser = _ArchiveDataParser()
    parser.feed(source.read_text(encoding="utf-8"))
    parser.close()
    if parser.payload is None:
        raise ValueError(f"不是有效的 DiskHTML 快照：{source}")
    payload = parser.payload
    if payload.get("format_version") != _ARCHIVE_FORMAT_VERSION or payload.get("kind") != "scan":
        raise ValueError(f"不是受支持的 DiskHTML 快照：{source}")
    if not isinstance(payload.get("files"), list):
        raise ValueError(f"快照缺少文件清单：{source}")
    return payload


def _scan_payload(database: Database, scan_id: str) -> dict[str, Any]:
    """从临时 SQLite 索引提取可嵌入 HTML 的快照数据。"""

    scan = database.get_scan(scan_id)
    if scan is None or scan["status"] != "COMPLETED":
        raise ValueError("只能生成已完成的快照")
    return {
        "format_version": _ARCHIVE_FORMAT_VERSION,
        "kind": "scan",
        "generated_at": utc_now(),
        "scan": _row_to_dict(scan),
        "volume": _row_to_dict(database.get_volume(scan_id)),
        "statistics": database.summary(scan_id),
        "directories": [_row_to_dict(row) for row in database.iter_directories(scan_id)],
        "files": [_row_to_dict(row) for row in database.iter_files(scan_id)],
    }


def _snapshot_identity(payload: dict[str, Any], path: Path | str) -> dict[str, Any]:
    """提取比较报告所需的快照来源和扫描信息。"""

    scan = payload.get("scan")
    return {
        "path": str(Path(path)),
        "scan_id": scan.get("id") if isinstance(scan, dict) else None,
        "source_path": scan.get("source_path") if isinstance(scan, dict) else None,
        "generated_at": payload.get("generated_at"),
    }


def _ordered_files(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """按兼容 Windows 大小写规则的路径键输出快照文件。"""

    files = payload["files"]
    if not all(isinstance(item, dict) and "relative_path" in item for item in files):
        raise ValueError("快照的文件清单格式无效")
    yield from sorted(
        files, key=lambda item: str(item.get("path_key") or item["relative_path"].casefold())
    )


def sqlite_snapshot_path(output_path: Path | str) -> Path:
    """返回与 HTML 快照同名的 SQLite 索引路径。"""

    return Path(output_path).with_suffix(".sqlite3")


def _prepare_sqlite_destination(html_destination: Path) -> Path:
    """校验随 HTML 一起交付的 SQLite 索引不会覆盖已有快照。"""

    destination = sqlite_snapshot_path(html_destination)
    if destination.exists():
        raise FileExistsError(f"SQLite 快照已存在，拒绝覆盖：{destination}")
    return destination


def _remove_sqlite_artifacts(database_path: Path) -> None:
    """仅在 HTML 未发布时清理本次创建失败的同名 SQLite 临时产物。"""

    for candidate in (database_path, Path(f"{database_path}-wal"), Path(f"{database_path}-shm")):
        candidate.unlink(missing_ok=True)


def _prepare_destination(output_path: Path | str) -> Path:
    """校验单文件交付目标，拒绝覆盖已有 HTML。"""

    destination = Path(output_path)
    if destination.suffix.lower() != ".html":
        raise ValueError("HTML 快照和比较报告的输出文件必须使用 .html 扩展名")
    if destination.exists():
        raise FileExistsError(f"输出 HTML 已存在，拒绝覆盖：{destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _write_archive(destination: Path, payload: dict[str, Any], document: str) -> None:
    """以临时文件加原子替换发布单文件 HTML，避免暴露半成品。"""

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=destination.parent,
            prefix=f".{destination.name}.tmp-",
            suffix=".html",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(document)
            handle.write(_payload_script(payload))
            handle.write(_document_footer())
        if destination.exists():
            raise FileExistsError(f"输出 HTML 已存在，拒绝覆盖：{destination}")
        _publish_file(Path(temporary_name), destination)
    except BaseException:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise


def _publish_file(temporary: Path, destination: Path) -> None:
    """在 Windows 短暂占用文件时有限重试单文件发布。"""

    for attempt in range(3):
        try:
            os.replace(temporary, destination)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.05 * (attempt + 1))


def _payload_script(payload: dict[str, Any]) -> str:
    """将数据安全嵌入 HTML，不让路径文本提前终止 script 标签。"""

    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f'<script id="{_ARCHIVE_DATA_ID}" type="application/json">{encoded}</script>'


def _page_header(title: str, description: str) -> str:
    """\u8fd4\u56de\u5355\u6587\u4ef6\u79bb\u7ebf\u9875\u9762\u7684\u684c\u9762\u6587\u4ef6\u6d4f\u89c8\u5668\u9876\u90e8\u6846\u67b6\u3002"""

    return _ui_page_header(title, description)


def _scan_document(payload: dict[str, Any]) -> str:
    """\u751f\u6210\u5305\u542b\u5d4c\u5165\u6570\u636e\u7684\u79bb\u7ebf\u5feb\u7167\u6d4f\u89c8\u9875\u9762\u3002"""

    return _page_header(
        f"DiskHTML \u5feb\u7167 - {payload['scan']['source_path']}",
        "\u79bb\u7ebf\u6587\u4ef6\u5feb\u7167\uff0c\u4fdd\u7559 SHA-256 \u548c\u76ee\u5f55\u5bfc\u822a\u3002",
    ) + _tree_document(payload)


def _compare_document(payload: dict[str, Any]) -> str:
    """\u751f\u6210\u4e0e\u5feb\u7167\u6d4f\u89c8\u9875\u4e00\u81f4\u3001\u989d\u5916\u663e\u793a\u72b6\u6001\u5217\u7684\u6bd4\u8f83\u62a5\u544a\u3002"""

    return _page_header(
        "DiskHTML \u5feb\u7167\u6bd4\u8f83",
        "\u72b6\u6001\u5217\u663e\u793a\u5f53\u524d\u76ee\u5f55\u4e0e\u5feb\u7167\u76ee\u5f55\u7684\u6bd4\u8f83\u7ed3\u679c\u3002",
    ) + _tree_document(payload)


def _format_size(value: object) -> str:
    """\u5c06\u5b57\u8282\u6570\u8f6c\u6362\u4e3a\u9759\u6001\u56de\u9000\u8868\u683c\u4f7f\u7528\u7684\u6613\u8bfb\u5355\u4f4d\u3002"""
    if value is None:
        return "\u2014"
    number = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    unit = 0
    while number >= 1024 and unit < len(units) - 1:
        number /= 1024
        unit += 1
    return f"{number:.1f} {units[unit]}" if unit else f"{number:.0f} B"


def _initial_table_rows(payload: dict[str, Any]) -> str:
    """\u9884\u5148\u5199\u5165\u6761\u76ee\uff0c\u786e\u4fdd\u6d4f\u89c8\u5668\u811a\u672c\u5f02\u5e38\u65f6\u62a5\u544a\u4e0d\u4f1a\u663e\u793a\u4e3a\u7a7a\u3002"""
    compare = payload.get("kind") == "compare"
    entries = payload.get("entries", []) if compare else payload.get("files", [])
    rows: list[str] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        if compare:
            current = item.get("new_size_bytes") is not None
            size = item.get("new_size_bytes") if current else item.get("old_size_bytes")
            modified = item.get("new_modified_time") if current else item.get("old_modified_time")
            created = item.get("new_created_time") if current else item.get("old_created_time")
            digest = item.get("new_sha256") if current else item.get("old_sha256")
            same = str(item.get("status") or "ERROR")
        else:
            size = item.get("size_bytes")
            modified = item.get("modified_time")
            created = item.get("created_time")
            digest = item.get("sha256")
            same = ""
        values = (
            item.get("relative_path") or "(未命名文件)",
            _format_size(size),
            modified or "\u2014",
            created or "\u2014",
            digest or "\u2014",
            same,
        )
        rows.append(
            "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in values) + "</tr>"
        )
    return "".join(rows) or '<tr><td colspan="6">当前范围没有文件。</td></tr>'


def _tree_document(payload: dict[str, Any]) -> str:
    """\u8fd4\u56de\u684c\u9762\u6587\u4ef6\u6d4f\u89c8\u5668\u7684\u76ee\u5f55\u6811\u3001\u5217\u8868\u548c\u72b6\u6001\u680f\u3002"""

    return _ui_tree_document(payload, _initial_table_rows(payload))


def _document_footer() -> str:
    """\u8fd4\u56de\u79bb\u7ebf\u76ee\u5f55\u6d4f\u89c8\u3001\u641c\u7d22\u3001\u6392\u5e8f\u548c\u5bfc\u51fa\u811a\u672c\u3002"""

    return _ui_document_footer()


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    """将 SQLite Row 转换为可 JSON 序列化的字典。"""

    return dict(row) if row is not None else None


class _ArchiveDataParser(HTMLParser):
    """仅提取本项目写入的 JSON 数据脚本，避免依赖页面的其他内容。"""

    def __init__(self) -> None:
        super().__init__()
        self._inside_data = False
        self._chunks: list[str] = []
        self.payload: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """识别具有固定标识的 JSON script 标签。"""

        self._inside_data = tag == "script" and dict(attrs).get("id") == _ARCHIVE_DATA_ID

    def handle_data(self, data: str) -> None:
        """收集 JSON script 中的原始文本。"""

        if self._inside_data:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        """在 JSON script 结束时解析并保存快照数据。"""

        if tag != "script" or not self._inside_data:
            return
        self._inside_data = False
        try:
            parsed = json.loads("".join(self._chunks))
        except json.JSONDecodeError as exc:
            raise ValueError("HTML 快照中的数据损坏") from exc
        if not isinstance(parsed, dict):
            raise ValueError("HTML 快照中的数据格式无效")
        self.payload = parsed
        self._chunks.clear()

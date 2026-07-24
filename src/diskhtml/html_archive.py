"""单文件 HTML 冷备与快照比较服务。"""

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

from .compare import _iter_entries
from .config import ScanConfig
from .database import Database
from .models import CompareStatus, ScanProgress
from .scanner import ScanController, Scanner
from .util import utc_now

_ARCHIVE_FORMAT_VERSION = 1
_ARCHIVE_DATA_ID = "diskhtml-archive-data"
_RENDER_LIMIT = 500


def create_html_backup(
    source: Path | str,
    output_path: Path | str,
    options: ScanConfig | None = None,
    progress_callback: Callable[[ScanProgress], None] | None = None,
    controller: ScanController | None = None,
) -> Path:
    """扫描源路径并生成单个、可离线打开的可视化 HTML 冷备快照。"""

    destination = _prepare_destination(output_path)
    with tempfile.TemporaryDirectory(prefix="diskhtml-") as temporary_directory:
        database_path = Path(temporary_directory) / "transient-index.sqlite3"
        with Database(database_path) as database:
            scan_id = Scanner(database, progress_callback).start(
                Path(source), options or ScanConfig(), controller
            )
            payload = _scan_payload(database, scan_id)
            _write_archive(destination, payload, _scan_document(payload))
    return destination


def compare_html_archives(
    left_path: Path | str, right_path: Path | str, output_path: Path | str
) -> Path:
    """兼容比较两个 HTML 冷备快照，并生成单文件 HTML 报告。"""

    destination = _prepare_destination(output_path)
    left = read_html_backup(left_path)
    right = read_html_backup(right_path)
    _write_archive(
        destination,
        _compare_payload(
            left,
            right,
            _snapshot_identity(left, left_path),
            _snapshot_identity(right, right_path),
        ),
        _compare_document(),
    )
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
    """将 HTML 冷备中选定目录与本机目录比较，并生成可视化 HTML 报告。"""

    destination = _prepare_destination(output_path)
    archive = read_html_backup(archive_path)
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
    _write_archive(
        destination,
        _compare_payload(left, right, left_identity, right_identity),
        _compare_document(),
    )
    return destination


def html_backup_directories(path: Path | str) -> tuple[str, ...]:
    """返回 HTML 冷备内可供用户选择的目录，根目录以空字符串表示。"""

    return _directories_from_payload(read_html_backup(path))


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
        "entries": entries,
    }


def _selected_directory_payload(payload: dict[str, Any], directory: str) -> dict[str, Any]:
    """从冷备中截取指定目录，并将其重定根以与本机目录对齐。"""

    if directory not in _directories_from_payload(payload):
        raise ValueError(f"冷备中不存在所选目录：{directory or '根目录'}")
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
    return {**payload, "files": selected}


def _directories_from_payload(payload: dict[str, Any]) -> tuple[str, ...]:
    """从已解析的冷备数据推导可选择目录，供内部选择逻辑复用。"""

    return html_backup_directories_from_rows(payload)


def html_backup_directories_from_rows(payload: dict[str, Any]) -> tuple[str, ...]:
    """基于快照记录产生目录集合，兼容早期不含 directories 的冷备。"""

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
        raise ValueError("冷备目录不能包含上级路径")
    return normalized


def read_html_backup(path: Path | str) -> dict[str, Any]:
    """读取并校验 DiskHTML 单文件冷备快照中的嵌入数据。"""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"找不到 HTML 冷备快照：{source}")
    parser = _ArchiveDataParser()
    parser.feed(source.read_text(encoding="utf-8"))
    parser.close()
    if parser.payload is None:
        raise ValueError(f"不是有效的 DiskHTML 冷备快照：{source}")
    payload = parser.payload
    if payload.get("format_version") != _ARCHIVE_FORMAT_VERSION or payload.get("kind") != "scan":
        raise ValueError(f"不是受支持的 DiskHTML 冷备快照：{source}")
    if not isinstance(payload.get("files"), list):
        raise ValueError(f"冷备快照缺少文件清单：{source}")
    return payload


def _scan_payload(database: Database, scan_id: str) -> dict[str, Any]:
    """从临时 SQLite 索引提取可嵌入 HTML 的冷备快照数据。"""

    scan = database.get_scan(scan_id)
    if scan is None or scan["status"] != "COMPLETED":
        raise ValueError("只能生成已完成的冷备快照")
    return {
        "format_version": _ARCHIVE_FORMAT_VERSION,
        "kind": "scan",
        "generated_at": utc_now(),
        "scan": _row_to_dict(scan),
        "volume": _row_to_dict(database.get_volume(scan_id)),
        "statistics": database.summary(scan_id),
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
        raise ValueError("冷备快照的文件清单格式无效")
    yield from sorted(
        files, key=lambda item: str(item.get("path_key") or item["relative_path"].casefold())
    )


def _prepare_destination(output_path: Path | str) -> Path:
    """校验单文件交付目标，拒绝覆盖已有 HTML。"""

    destination = Path(output_path)
    if destination.suffix.lower() != ".html":
        raise ValueError("HTML 冷备和比较报告的输出文件必须使用 .html 扩展名")
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
    """返回包含可视化样式和页面标题的单文件 HTML 起始部分。"""

    safe_title = html.escape(title)
    safe_description = html.escape(description)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title}</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#1d2939;max-width:1280px}} input{{width:min(100%,46rem);padding:.55rem}} table{{border-collapse:collapse;width:100%;margin-top:1rem}} td,th{{border:1px solid #d0d5dd;padding:.45rem;text-align:left;vertical-align:top;word-break:break-word}} .muted{{color:#667085}} #status{{margin:.8rem 0}} button{{margin-right:.4rem;padding:.4rem .7rem;cursor:pointer}} pre{{white-space:pre-wrap;background:#f8fafc;padding:1rem;overflow:auto}} .content-grid{{display:grid;grid-template-columns:minmax(15rem,22rem) minmax(0,1fr);gap:1.25rem;align-items:start}} .tree-pane{{border:1px solid #d0d5dd;border-radius:.5rem;padding:.75rem;max-height:70vh;overflow:auto;position:sticky;top:1rem}} .tree-pane h2{{font-size:1rem;margin:.1rem 0 .65rem}} .tree-root,.tree-folder{{margin:.2rem 0}} .tree-folder>summary{{cursor:pointer;list-style:none}} .tree-folder>summary::-webkit-details-marker{{display:none}} .tree-folder>summary::before{{content:"▸ ";}} .tree-folder[open]>summary::before{{content:"▾ ";}} .tree-children{{margin-left:1rem}} .tree-select{{border:0;background:transparent;color:#175cd3;padding:.15rem .25rem;text-align:left;max-width:100%;word-break:break-word}} .tree-select.active{{background:#d1e9ff;border-radius:.25rem;font-weight:600}} @media(max-width:760px){{.content-grid{{grid-template-columns:1fr}} .tree-pane{{position:static;max-height:20rem}}}}
</style>
</head>
<body>
<h1>{safe_title}</h1>
<p id="summary"></p>
<p class="muted">{safe_description}</p>
"""


def _scan_document(payload: dict[str, Any]) -> str:
    """生成冷备快照的静态页面外壳。"""

    return (
        _page_header(
            f"DiskHTML 冷备快照 - {payload['scan']['source_path']}",
            "这是可独立保存和离线打开的 HTML 冷备快照；SQLite 仅在生成期间作为临时索引，不会随快照交付。",
        )
        + _tree_document()
        + _scan_table_document("按路径、状态或错误信息筛选")
        + "</main></div>"
    )


def _tree_document() -> str:
    """返回冷备快照专用的可展开目录树布局。"""

    return """<div class="content-grid"><aside class="tree-pane"><h2>文件树</h2><p class="muted">展开目录，单击目录名筛选右侧文件。</p><div id="tree"></div></aside><main>"""


def _compare_document() -> str:
    """生成快照比较报告的静态页面外壳。"""

    return (
        _page_header(
            "DiskHTML 冷备比较报告",
            "左侧为 HTML 冷备中选定的历史目录，右侧为本机目录。报告可独立保存和离线打开。",
        )
        + """<div id="sources" class="muted"></div>
<p><button type="button" data-status="">全部</button><button type="button" data-status="MATCH">MATCH</button><button type="button" data-status="CHANGED">CHANGED</button><button type="button" data-status="ADDED">ADDED</button><button type="button" data-status="MISSING">MISSING</button><button type="button" data-status="ERROR">ERROR</button></p>
"""
        + _table_document("按路径、状态或错误信息筛选")
    )


def _scan_table_document(placeholder: str) -> str:
    """返回冷备快照的 SHA-256 文件列表结构。"""

    return f"""<input id="filter" type="search" placeholder="{html.escape(placeholder)}">
<p id="status" class="muted"></p>
<table><thead><tr><th>路径</th><th>Hash 状态</th><th>大小（字节）</th><th>SHA-256</th><th>错误</th></tr></thead><tbody id="rows"></tbody></table>
<button id="more" type="button">显示更多</button>
<h2>选中条目详情</h2><pre id="detail" class="muted">选择一条记录查看详情。</pre>
"""


def _table_document(placeholder: str) -> str:
    """返回包含筛选、分页和详情区域的共享可视化结构。"""

    return f"""<input id="filter" type="search" placeholder="{html.escape(placeholder)}">
<p id="status" class="muted"></p>
<table><thead><tr><th>路径</th><th>状态</th><th>旧/当前大小</th><th>新大小/摘要</th><th>错误</th></tr></thead><tbody id="rows"></tbody></table>
<button id="more" type="button">显示更多</button>
<h2>选中条目详情</h2><pre id="detail" class="muted">选择一条记录查看详情。</pre>
"""


def _document_footer() -> str:
    """返回所有单文件报告共用的安全渲染脚本。"""

    return """<script>
(() => {
  const payload = JSON.parse(document.getElementById('diskhtml-archive-data').textContent);
  const rowsElement = document.getElementById('rows');
  const filter = document.getElementById('filter');
  const status = document.getElementById('status');
  const detail = document.getElementById('detail');
  const more = document.getElementById('more');
  const limit = 500;
  let shown = limit;
  let selectedStatus = '';
  const records = payload.kind === 'scan' ? payload.files : payload.entries;
  const tree = document.getElementById('tree');
  let selectedDirectory = '';

  function selectedLabel() {
    return selectedDirectory || '全部目录';
  }

  function inSelectedDirectory(record) {
    return !selectedDirectory || record.relative_path.startsWith(selectedDirectory + '/');
  }

  function selectDirectory(path) {
    selectedDirectory = path;
    tree?.querySelectorAll('.tree-select').forEach((element) => {
      element.classList.toggle('active', element.dataset.path === path);
    });
    shown = limit;
    render();
  }

  function createTree() {
    if (!tree || payload.kind !== 'scan') return;
    const root = { path: '', children: new Map() };
    function addDirectory(path) {
      let node = root;
      let fullPath = '';
      for (const part of path.split('/').filter(Boolean)) {
        fullPath = fullPath ? fullPath + '/' + part : part;
        if (!node.children.has(part)) node.children.set(part, { path: fullPath, children: new Map() });
        node = node.children.get(part);
      }
    }
    (payload.directories || []).forEach((directory) => addDirectory(directory.relative_path || ''));
    records.forEach((record) => addDirectory(record.relative_path.split('/').slice(0, -1).join('/')));
    function selectButton(label, path) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'tree-select' + (path === selectedDirectory ? ' active' : '');
      button.dataset.path = path;
      button.textContent = label;
      button.addEventListener('click', (event) => { event.stopPropagation(); selectDirectory(path); });
      return button;
    }
    function appendChildren(parent, node, depth) {
      const children = [...node.children.values()].sort((left, right) => left.path.localeCompare(right.path, 'zh-CN'));
      const container = document.createElement('div');
      container.className = depth ? 'tree-children' : 'tree-root';
      children.forEach((child) => {
        const details = document.createElement('details');
        details.className = 'tree-folder';
        details.open = depth < 1;
        const summary = document.createElement('summary');
        summary.appendChild(selectButton('📁 ' + child.path.split('/').at(-1), child.path));
        details.appendChild(summary);
        appendChildren(details, child, depth + 1);
        container.appendChild(details);
      });
      parent.appendChild(container);
    }
    tree.replaceChildren();
    tree.appendChild(selectButton('🗀 冷备根目录', ''));
    appendChildren(tree, root, 0);
  }

  function values(record) {
    if (payload.kind === 'scan') {
      return [record.relative_path, record.hash_status, record.size_bytes, record.sha256 || '', record.error_message || ''];
    }
    return [record.relative_path, record.status, record.old_size_bytes ?? '', record.new_size_bytes ?? '', record.error_message || ''];
  }

  function currentRecords() {
    const needle = filter.value.trim().toLocaleLowerCase();
    return records.filter((record) => {
      const text = values(record).join(' ').toLocaleLowerCase();
      return inSelectedDirectory(record) && (!selectedStatus || record.status === selectedStatus) && (!needle || text.includes(needle));
    });
  }

  function render() {
    const current = currentRecords();
    rowsElement.replaceChildren();
    for (const record of current.slice(0, shown)) {
      const tr = document.createElement('tr');
      tr.addEventListener('click', () => { detail.textContent = JSON.stringify(record, null, 2); });
      for (const value of values(record)) {
        const td = document.createElement('td');
        td.textContent = value;
        tr.append(td);
      }
      rowsElement.append(tr);
    }
    status.textContent = '目录：' + selectedLabel() + '；显示 ' + Math.min(shown, current.length) + ' / ' + current.length + ' 条记录';
    more.hidden = shown >= current.length;
  }

  if (payload.kind === 'scan') {
    const stats = payload.statistics;
    document.getElementById('summary').textContent = '文件 ' + stats.total_files + '，目录 ' + stats.total_directories + '，已 Hash ' + stats.hashed_files + '，问题 ' + stats.problem_files;
  } else {
    document.getElementById('summary').textContent = Object.entries(payload.statistics).map(([key, value]) => key + ' ' + value).join('，');
    document.getElementById('sources').textContent = '历史冷备：' + payload.left.path + '（目录：' + payload.left.selected_directory + '）；本机目录：' + payload.right.path;
    document.querySelectorAll('[data-status]').forEach((button) => {
      button.addEventListener('click', () => { selectedStatus = button.dataset.status; shown = limit; render(); });
    });
  }
  filter.addEventListener('input', () => { shown = limit; render(); });
  more.addEventListener('click', () => { shown += limit; render(); });
  createTree();
  render();
})();
</script>
</body>
</html>
"""


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
            raise ValueError("HTML 冷备快照中的数据损坏") from exc
        if not isinstance(parsed, dict):
            raise ValueError("HTML 冷备快照中的数据格式无效")
        self.payload = parsed
        self._chunks.clear()

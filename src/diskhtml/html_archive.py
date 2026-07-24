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


def render_html_from_sqlite(database_path: Path | str, output_path: Path | str) -> Path:
    """从已保存的 SQLite 冷备索引重新生成当前版本的 HTML 页面。"""

    destination = _prepare_destination(output_path)
    with Database.open_existing(database_path) as database:
        latest = database.latest_scan()
        if latest is None:
            raise ValueError("SQLite 冷备中没有可用于生成 HTML 的已完成扫描")
        payload = _scan_payload(database, str(latest["id"]))
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
        raise ValueError("冷备快照的文件清单格式无效")
    yield from sorted(
        files, key=lambda item: str(item.get("path_key") or item["relative_path"].casefold())
    )


def sqlite_backup_path(output_path: Path | str) -> Path:
    """返回与 HTML 冷备同名的 SQLite 索引路径。"""

    return Path(output_path).with_suffix(".sqlite3")


def _prepare_sqlite_destination(html_destination: Path) -> Path:
    """校验随 HTML 一起交付的 SQLite 索引不会覆盖已有冷备。"""

    destination = sqlite_backup_path(html_destination)
    if destination.exists():
        raise FileExistsError(f"SQLite 冷备已存在，拒绝覆盖：{destination}")
    return destination


def _remove_sqlite_artifacts(database_path: Path) -> None:
    """仅在 HTML 未发布时清理本次创建失败的同名 SQLite 临时产物。"""

    for candidate in (database_path, Path(f"{database_path}-wal"), Path(f"{database_path}-shm")):
        candidate.unlink(missing_ok=True)


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
body{{font:14px system-ui,sans-serif;margin:2rem;color:#1d2939;max-width:1280px}} input{{width:min(100%,46rem);padding:.55rem}} table{{border-collapse:collapse;width:100%;margin-top:1rem}} td,th{{border:1px solid #d0d5dd;padding:.45rem;text-align:left;vertical-align:top;word-break:break-word}} .muted{{color:#667085}} #status{{margin:.8rem 0}} button{{margin-right:.4rem;padding:.4rem .7rem;cursor:pointer}} pre{{white-space:pre-wrap;background:#f8fafc;padding:1rem;overflow:auto}} .content-grid{{display:grid;grid-template-columns:minmax(16rem,24rem) minmax(0,1fr);gap:1.25rem;align-items:start}} .tree-pane{{border:1px solid #d0d5dd;border-radius:.5rem;padding:.75rem;max-height:72vh;overflow:auto;position:sticky;top:1rem}} .tree-pane h2{{font-size:1rem;margin:.1rem 0 .65rem}} .tree-folder{{margin:.2rem 0}} .tree-folder>summary{{cursor:pointer;list-style:none}} .tree-folder>summary::-webkit-details-marker{{display:none}} .tree-folder>summary::before{{content:"▸ ";}} .tree-folder[open]>summary::before{{content:"▾ ";}} .tree-children{{margin-left:1rem}} .tree-select,.name-link{{border:0;background:transparent;color:#175cd3;padding:.18rem .25rem;text-align:left;cursor:pointer}} .tree-select.active{{background:#d1e9ff;border-radius:.25rem;font-weight:600}} .diff-dot{{display:inline-block;width:.55rem;height:.55rem;border-radius:50%;background:#d92d20;margin-left:.35rem}} .metadata{{display:grid;grid-template-columns:max-content 1fr;gap:.45rem 1rem;background:#f8fafc;padding:1rem}} .metadata dt{{font-weight:600}} .metadata dd{{margin:0;word-break:break-word}} .status-filter{{display:flex;flex-wrap:wrap;gap:.35rem}} @media(max-width:760px){{.content-grid{{grid-template-columns:1fr}} .tree-pane{{position:static;max-height:20rem}}}} .content-grid{{display:grid;grid-template-columns:minmax(15rem,22rem) minmax(0,1fr);gap:1.25rem;align-items:start}} .tree-pane{{border:1px solid #d0d5dd;border-radius:.5rem;padding:.75rem;max-height:70vh;overflow:auto;position:sticky;top:1rem}} .tree-pane h2{{font-size:1rem;margin:.1rem 0 .65rem}} .tree-root,.tree-folder{{margin:.2rem 0}} .tree-folder>summary{{cursor:pointer;list-style:none}} .tree-folder>summary::-webkit-details-marker{{display:none}} .tree-folder>summary::before{{content:"▸ ";}} .tree-folder[open]>summary::before{{content:"▾ ";}} .tree-children{{margin-left:1rem}} .tree-select{{border:0;background:transparent;color:#175cd3;padding:.15rem .25rem;text-align:left;max-width:100%;word-break:break-word}} .tree-select.active{{background:#d1e9ff;border-radius:.25rem;font-weight:600}} @media(max-width:760px){{.content-grid{{grid-template-columns:1fr}} .tree-pane{{position:static;max-height:20rem}}}}
</style>
</head>
<body>
<h1>{safe_title}</h1>
<p id="summary"></p>
<p class="muted">{safe_description}</p>
"""


def _scan_document(payload: dict[str, Any]) -> str:
    """生成类似文件管理器的树形冷备快照页面。"""

    return (
        _page_header(
            f"DiskHTML 冷备快照 - {payload['scan']['source_path']}",
            "单击左侧或右侧文件夹浏览内容；每个文件均保留 SHA-256。",
        )
        + _tree_document()
        + "</main></div>"
    )


def _compare_document() -> str:
    """生成与冷备快照同布局、带差异红点的比较报告。"""

    return (
        _page_header(
            "DiskHTML 冷备比较报告",
            "红点表示该文件夹或其后代存在不同文件。",
        )
        + """<div id="sources" class="muted"></div>
<p class="status-filter"><button type="button" data-status="">全部</button><button type="button" data-status="MATCH">MATCH</button><button type="button" data-status="CHANGED">CHANGED</button><button type="button" data-status="ADDED">ADDED</button><button type="button" data-status="MISSING">MISSING</button><button type="button" data-status="ERROR">ERROR</button></p>
"""
        + _tree_document()
        + "</main></div>"
    )


def _tree_document() -> str:
    """返回快照与比较报告共用的树形导航和右侧详情框架。"""

    return """<div class="content-grid"><aside class="tree-pane"><h2>文件树</h2><p class="muted">单击文件夹查看内容；红点表示存在不同文件。</p><div id="tree"></div></aside><main>
<input id="filter" type="search" placeholder="按名称、摘要或状态筛选">
<p id="status" class="muted"></p>
<h2 id="detail-title">目录详情：冷备根目录</h2>
<table><thead><tr><th>Name</th><th>Size</th><th>Modified</th><th>Created</th><th>SHA-256</th><th id="same-heading">是否相同</th></tr></thead><tbody id="rows"></tbody></table>
<button id="more" type="button">显示更多</button>
<h2>选中条目详情</h2><dl id="detail" class="metadata"><dt>提示</dt><dd>选择文件或文件夹查看完整元数据。</dd></dl>
"""


def _document_footer() -> str:
    """返回离线树形详情、目录点击和比较差异红点渲染脚本。"""

    return """<script>
(() => {
  // 所有数据均嵌入单文件 HTML，浏览时不请求网络或本机路径。
  const payload = JSON.parse(document.getElementById('diskhtml-archive-data').textContent);
  const tree = document.getElementById('tree'), rows = document.getElementById('rows');
  const filter = document.getElementById('filter'), status = document.getElementById('status');
  const title = document.getElementById('detail-title'), detail = document.getElementById('detail');
  const more = document.getElementById('more'), sameHeading = document.getElementById('same-heading');
  let selectedPath = '', selectedRecord = null, shown = 500, selectedStatus = '';
  const mode = payload.kind;
  const records = mode === 'scan' ? (payload.files || []).map(scanRecord) : (payload.entries || []).map(compareRecord);
  const directories = (payload.directories || []).map((row) => ({...row}));
  const nameOf = (path) => String(path || '').split('/').filter(Boolean).at(-1) || '冷备根目录';
  const parentOf = (path) => { const parts = String(path || '').split('/').filter(Boolean); parts.pop(); return parts.join('/'); };
  const under = (base, path) => !base || path === base || path.startsWith(base + '/');
  const size = (value) => { if (value === null || value === undefined) return '—'; const units=['B','KB','MB','GB','TB']; let number=Number(value),unit=0; while(number>=1024&&unit<4){number/=1024;unit++;} return (unit ? number.toFixed(number>=10?1:2) : Math.round(number))+' '+units[unit]; };
  const time = (value) => { if (!value) return '—'; const date=new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN',{hour12:false}); };
  function scanRecord(row) { return {kind:'file',relative_path:String(row.relative_path||''),name:row.name||nameOf(row.relative_path),size_bytes:row.size_bytes,modified_time:row.modified_time,created_time:row.created_time,sha256:row.sha256,status:row.hash_status||'UNKNOWN',error_message:row.error_message||'',raw:row}; }
  function compareRecord(row) { const current=row.new_size_bytes!==null&&row.new_size_bytes!==undefined; return {kind:'file',relative_path:String(row.relative_path||''),name:nameOf(row.relative_path),size_bytes:current?row.new_size_bytes:row.old_size_bytes,modified_time:current?row.new_modified_time:row.old_modified_time,created_time:current?row.new_created_time:row.old_created_time,sha256:current?row.new_sha256:row.old_sha256,status:row.status||'ERROR',error_message:row.error_message||'',raw:row}; }
  function paths() { const result=new Set(['']); directories.forEach((row)=>result.add(String(row.relative_path||''))); records.forEach((row)=>{let path=parentOf(row.relative_path);while(true){result.add(path);if(!path)break;path=parentOf(path);}});return [...result]; }
  function folder(path) { const raw=directories.find((row)=>String(row.relative_path||'')===path)||{}; const descendants=records.filter((row)=>under(path,row.relative_path)); const different=mode==='compare'&&descendants.some((row)=>row.status!=='MATCH'); return {kind:'directory',relative_path:path,name:nameOf(path),size_bytes:descendants.reduce((total,row)=>total+(Number(row.size_bytes)||0),0),modified_time:raw.modified_time,created_time:raw.created_time,sha256:null,status:different?'DIFFERENT':'MATCH',raw}; }
  function different(path) { return mode==='compare'&&records.some((row)=>under(path,row.relative_path)&&row.status!=='MATCH'); }
  function same(row) { if(mode!=='compare')return ''; return row.kind==='directory' ? (row.status==='MATCH'?'是':'否') : (row.status==='MATCH'?'是':'否（'+row.status+'）'); }
  function visible() { const needle=filter.value.trim().toLocaleLowerCase(); const folders=paths().filter((path)=>path&&parentOf(path)===selectedPath).map(folder); const files=records.filter((row)=>parentOf(row.relative_path)===selectedPath); return [...folders,...files].filter((row)=>{const text=[row.name,row.sha256||'',row.status||'',row.error_message||''].join(' ').toLocaleLowerCase();const state=!selectedStatus||(row.kind==='directory'?(selectedStatus==='MATCH'?row.status==='MATCH':row.status==='DIFFERENT'):row.status===selectedStatus);return state&&(!needle||text.includes(needle));}).sort((left,right)=>left.kind===right.kind?left.name.localeCompare(right.name,'zh-CN'):left.kind==='directory'?-1:1); }
  function dot() { const item=document.createElement('span');item.className='diff-dot';item.title='存在不同文件';return item; }
  function select(path,record=null) { selectedPath=path;selectedRecord=record||folder(path);shown=500;render(); }
  function renderTree() { const root={path:'',children:new Map()}; function ensure(path){let node=root,full='';String(path||'').split('/').filter(Boolean).forEach((part)=>{full=full?full+'/'+part:part;if(!node.children.has(part))node.children.set(part,{path:full,children:new Map()});node=node.children.get(part);});return node;} paths().forEach(ensure); function append(parent,node,depth){const item=document.createElement('details');item.className='tree-folder';item.open=depth<1;const summary=document.createElement('summary');const button=document.createElement('button');button.type='button';button.className='tree-select'+(node.path===selectedPath?' active':'');button.textContent='📁 '+nameOf(node.path);button.addEventListener('click',(event)=>{event.stopPropagation();select(node.path);});summary.append(button);if(different(node.path))summary.append(dot());item.append(summary);const children=document.createElement('div');children.className='tree-children';[...node.children.values()].sort((left,right)=>left.path.localeCompare(right.path,'zh-CN')).forEach((child)=>append(children,child,depth+1));item.append(children);parent.append(item);} tree.replaceChildren();append(tree,root,0); }
  function showDetail(row) { const fields=[['Name',row.name],['Type',row.kind==='directory'?'文件夹':'文件'],['Size',size(row.size_bytes)],['Modified',time(row.modified_time)],['Created',time(row.created_time)],['SHA-256',row.sha256||'—']];if(mode==='compare')fields.push(['是否相同',same(row)]);if(row.error_message)fields.push(['错误',row.error_message]);detail.replaceChildren();fields.forEach(([key,value])=>{const term=document.createElement('dt'),definition=document.createElement('dd');term.textContent=key;definition.textContent=value||'—';detail.append(term,definition);}); }
  function render() { const current=visible();rows.replaceChildren();current.slice(0,shown).forEach((row)=>{const tableRow=document.createElement('tr');const label=document.createElement(row.kind==='directory'?'button':'span');label.textContent=(row.kind==='directory'?'📁 ':'📄 ')+row.name;label.className='name-link';if(row.kind==='directory'){label.type='button';label.addEventListener('click',()=>select(row.relative_path));}else{tableRow.addEventListener('click',()=>{selectedRecord=row;showDetail(row);});}[label,size(row.size_bytes),time(row.modified_time),time(row.created_time),row.sha256||'—',same(row)].forEach((value,index)=>{const cell=document.createElement('td');if(value instanceof Node)cell.append(value);else cell.textContent=value;if(index===5&&mode!=='compare')cell.hidden=true;tableRow.append(cell);});rows.append(tableRow);});sameHeading.hidden=mode!=='compare';title.textContent='目录详情：'+(selectedPath||'冷备根目录');status.textContent='目录：'+(selectedPath||'冷备根目录')+'；显示 '+Math.min(shown,current.length)+' / '+current.length+' 项';more.hidden=shown>=current.length;showDetail(selectedRecord||folder(selectedPath));renderTree(); }
  if(mode==='scan'){const stats=payload.statistics;document.getElementById('summary').textContent='文件 '+stats.total_files+'，目录 '+stats.total_directories+'，已 Hash '+stats.hashed_files+'，问题 '+stats.problem_files;}else{document.getElementById('summary').textContent=Object.entries(payload.statistics).map(([key,value])=>key+' '+value).join('，');document.getElementById('sources').textContent='历史冷备：'+payload.left.path+'（目录：'+payload.left.selected_directory+'）；本机目录：'+payload.right.path;document.querySelectorAll('[data-status]').forEach((button)=>button.addEventListener('click',()=>{selectedStatus=button.dataset.status;shown=500;render();}));}
  filter.addEventListener('input',()=>{shown=500;render();});more.addEventListener('click',()=>{shown+=500;render();});render();
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

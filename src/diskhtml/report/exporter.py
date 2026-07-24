"""从完成扫描流式生成可离线浏览的导出报告。"""

from __future__ import annotations

import csv
import html
import json
import os
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..database import Database
from ..util import utc_now

REPORT_FORMAT_VERSION = 1
_FILE_COLUMNS = (
    "relative_path",
    "path_key",
    "name",
    "extension",
    "size_bytes",
    "created_time",
    "modified_time",
    "mtime_ns",
    "hash_status",
    "sha256",
    "sha512",
    "attempt_count",
    "error_code",
    "error_message",
    "hashed_at",
)
_HASH_COLUMNS = ("relative_path", "size_bytes", "hash_status", "sha256", "sha512", "hashed_at")


def export_scan(database: Database, scan_id: str, output_path: Path | str) -> Path:
    """将已完成扫描导出到新目录，并通过原子改名完成发布。"""

    scan = database.get_scan(scan_id)
    if scan is None:
        raise ValueError(f"未找到扫描任务：{scan_id}")
    if scan["status"] != "COMPLETED":
        raise ValueError("只能导出已完成的扫描任务")

    destination = Path(output_path)
    if destination.exists():
        raise FileExistsError(f"导出目录已经存在：{destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    try:
        temporary.mkdir()
        _write_export(database, scan_id, temporary)
        os.replace(temporary, destination)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return destination


def _write_export(database: Database, scan_id: str, output: Path) -> None:
    """在临时目录中完成全部文件，避免暴露半成品报告。"""

    assets = output / "report_assets"
    shards = assets / "shards"
    shards.mkdir(parents=True)
    volume = database.get_volume(scan_id)
    summary = {
        "format_version": REPORT_FORMAT_VERSION,
        "generated_at": utc_now(),
        "scan_id": scan_id,
        "scan": _row_to_dict(database.get_scan(scan_id)),
        "statistics": database.summary(scan_id),
    }
    _write_json(output / "disk_info.json", _row_to_dict(volume))
    _write_json(output / "summary.json", summary)
    _write_csv(output / "file_list.csv", _FILE_COLUMNS, database.iter_files(scan_id))
    _write_csv(output / "hash_list.csv", _HASH_COLUMNS, database.iter_files(scan_id))
    manifest = _write_shards(database.iter_files(scan_id), shards)
    _write_assets(assets, manifest, summary)
    (output / "report.html").write_text(_report_html(summary), encoding="utf-8")


def _write_csv(path: Path, fields: tuple[str, ...], rows: Iterator[Any]) -> None:
    """以 UTF-8 BOM 流式写入 CSV，确保 Excel 正确识别中文。"""

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})


def _write_shards(rows: Iterator[Any], directory: Path) -> list[dict[str, str]]:
    """按顶级目录流式写入脚本分片，首屏不加载全量文件。"""

    manifest: list[dict[str, str]] = []
    active_key: str | None = None
    active_file: Any = None
    first_item = True

    def close_active() -> None:
        nonlocal active_file
        if active_file is not None:
            active_file.write("]);\n")
            active_file.close()
            active_file = None

    try:
        for row in rows:
            key, label = _shard_key(str(row["relative_path"]))
            if key != active_key:
                close_active()
                active_key = key
                filename = f"{len(manifest):05d}.js"
                manifest.append({"key": key, "label": label, "file": f"shards/{filename}"})
                active_file = (directory / filename).open("w", encoding="utf-8", newline="")
                active_file.write(
                    "window.DiskHtmlReport.registerShard("
                    + json.dumps(key, ensure_ascii=False)
                    + ",["
                )
                first_item = True
            if not first_item:
                active_file.write(",")
            active_file.write(
                json.dumps(_row_to_dict(row), ensure_ascii=False, separators=(",", ":"))
            )
            first_item = False
    finally:
        close_active()
    return manifest


def _shard_key(relative_path: str) -> tuple[str, str]:
    """按第一级相对路径分片，保证排序扫描时同一分片连续。"""

    parts = Path(relative_path).parts
    if len(parts) <= 1:
        return "__root__", "根目录文件"
    return parts[0], parts[0]


def _write_assets(assets: Path, manifest: list[dict[str, str]], summary: dict[str, Any]) -> None:
    """写入不依赖网络的样式、交互脚本和分片清单。"""

    (assets / "styles.css").write_text(
        "body{font:14px system-ui;margin:2rem;color:#1d2939;max-width:1200px}button{margin:.2rem;padding:.4rem .7rem;cursor:pointer}"
        "table{border-collapse:collapse;width:100%;margin-top:1rem}td,th{border:1px solid #d0d5dd;padding:.4rem;text-align:left;vertical-align:top}"
        "tr{cursor:pointer}.muted{color:#667085}#filter{width:min(100%,42rem);padding:.5rem}#tree ul{margin:.2rem 0 .2rem 1rem;padding:0}"
        "#tree li{list-style:none}#tree button{border:0;background:none;color:#175cd3;text-align:left}#detail{white-space:pre-wrap;background:#f9fafb;padding:1rem;overflow:auto}",
        encoding="utf-8",
    )
    (assets / "manifest.js").write_text(
        "window.DiskHtmlReportManifest="
        + json.dumps(
            {"shards": manifest, "summary": summary}, ensure_ascii=False, separators=(",", ":")
        )
        + ";\n",
        encoding="utf-8",
    )
    (assets / "app.js").write_text(_app_script(), encoding="utf-8")


def _app_script() -> str:
    """返回可直接由 file:// 加载的本地报告脚本。"""

    return """window.DiskHtmlReport={cache:{},registerShard:function(key,rows){this.cache[key]=rows;}};
(function(){
const m=window.DiskHtmlReportManifest,list=document.querySelector('#directories'),status=document.querySelector('#status'),tbody=document.querySelector('#files tbody'),tree=document.querySelector('#tree'),filter=document.querySelector('#filter'),detail=document.querySelector('#detail');let current=[];
document.querySelector('#summary').textContent='文件 '+m.summary.statistics.total_files+'，已 Hash '+m.summary.statistics.hashed_files+'，问题 '+m.summary.statistics.problem_files;
function describe(f){detail.textContent=JSON.stringify({路径:f.relative_path,大小:f.size_bytes,状态:f.hash_status,SHA256:f.sha256,错误代码:f.error_code,错误信息:f.error_message,修改时间:f.modified_time},null,2)}
function show(rows){tbody.replaceChildren();for(const f of rows){const tr=document.createElement('tr');tr.onclick=()=>describe(f);for(const v of [f.relative_path,f.size_bytes,f.hash_status,f.sha256||'',f.error_message||'']){const td=document.createElement('td');td.textContent=v;tr.append(td)}tbody.append(tr)}status.textContent='当前显示 '+rows.length+' 条文件记录'}
function buildTree(rows){const root={dirs:new Map(),files:[]};for(const f of rows){const parts=f.relative_path.split('/'),name=parts.pop();let node=root;for(const part of parts){if(!node.dirs.has(part))node.dirs.set(part,{dirs:new Map(),files:[]});node=node.dirs.get(part)}node.files.push(f)}function render(node){const ul=document.createElement('ul');for(const [name,child] of node.dirs){const li=document.createElement('li'),box=document.createElement('details'),summary=document.createElement('summary');summary.textContent=name;box.append(summary,render(child));li.append(box);ul.append(li)}for(const f of node.files){const li=document.createElement('li'),button=document.createElement('button');button.type='button';button.textContent=f.name;button.onclick=()=>describe(f);li.append(button);ul.append(li)}return ul}tree.replaceChildren(render(root))}
function apply(){const needle=filter.value.trim().toLocaleLowerCase();const rows=needle?current.filter(f=>(f.relative_path+' '+f.hash_status+' '+(f.error_message||'')).toLocaleLowerCase().includes(needle)):current;show(rows)}
filter.oninput=apply;
function select(rows){current=rows;filter.value='';buildTree(rows);show(rows)}
for(const s of m.shards){const b=document.createElement('button');b.type='button';b.textContent=s.label;b.onclick=()=>{if(window.DiskHtmlReport.cache[s.key]){select(window.DiskHtmlReport.cache[s.key]);return}const e=document.createElement('script');e.src='report_assets/'+s.file;e.onload=()=>select(window.DiskHtmlReport.cache[s.key]||[]);e.onerror=()=>status.textContent='无法加载本地分片：'+s.file;document.head.append(e)};list.append(b)}

})();"""


def _report_html(summary: dict[str, Any]) -> str:
    """生成固定且安全转义的报告首页。"""

    title = html.escape(f"DiskHTML 扫描报告 {summary['scan_id']}")
    return f"""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{title}</title><link rel=\"stylesheet\" href=\"report_assets/styles.css\"></head><body><h1>{title}</h1><p id=\"summary\"></p><h2>目录分片</h2><div id=\"directories\"></div><p id=\"status\" class=\"muted\">选择一个目录加载文件明细。</p><h2>目录树</h2><div id=\"tree\" class=\"muted\">尚未加载目录分片。</div><h2>搜索与筛选</h2><input id=\"filter\" type=\"search\" placeholder=\"按路径、状态或错误信息筛选当前分片\"><table id=\"files\"><thead><tr><th>路径</th><th>大小</th><th>状态</th><th>SHA256</th><th>错误</th></tr></thead><tbody></tbody></table><h2>文件详情</h2><pre id=\"detail\" class=\"muted\">选择文件查看详情。</pre><script src=\"report_assets/manifest.js\"></script><script src=\"report_assets/app.js\"></script></body></html>"""


def _write_json(path: Path, value: Any) -> None:
    """以 UTF-8 写入稳定缩进的 JSON。"""

    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    """把 sqlite Row 转换为 JSON 可序列化字典。"""

    return dict(row) if row is not None else None

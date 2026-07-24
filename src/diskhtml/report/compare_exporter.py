"""比较任务的 CSV 与离线报告导出。"""

from __future__ import annotations

import html
import json
import os
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..database import Database
from ..models import CompareStatus
from ..util import utc_now
from .exporter import _row_to_dict, _write_csv, _write_json

COMPARE_REPORT_FORMAT_VERSION = 1
_COMPARE_COLUMNS = (
    "relative_path",
    "status",
    "old_size_bytes",
    "new_size_bytes",
    "old_sha256",
    "new_sha256",
    "error_message",
)


def export_compare(database: Database, compare_id: str, output_path: Path | str) -> Path:
    """将已完成比较导出到新目录，并通过原子改名完成发布。"""

    compare = database.get_compare(compare_id)
    if compare is None:
        raise ValueError(f"未找到比较任务：{compare_id}")
    if compare["status"] != "COMPLETED":
        raise ValueError("只能导出已完成的比较任务")

    destination = Path(output_path)
    if destination.exists():
        raise FileExistsError(f"导出目录已经存在：{destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    try:
        temporary.mkdir()
        _write_compare_export(database, compare_id, temporary)
        os.replace(temporary, destination)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return destination


def _write_compare_export(database: Database, compare_id: str, output: Path) -> None:
    """在临时目录中写入比较 CSV、分片和离线报告。"""

    assets = output / "compare_assets"
    shards = assets / "shards"
    shards.mkdir(parents=True)
    compare = database.get_compare(compare_id)
    summary = {
        "format_version": COMPARE_REPORT_FORMAT_VERSION,
        "generated_at": utc_now(),
        "compare": _row_to_dict(compare),
        "statistics": json.loads(compare["summary_json"]),
    }
    _write_json(output / "compare_summary.json", summary)
    _write_csv(
        output / "compare_entries.csv", _COMPARE_COLUMNS, database.iter_compare_entries(compare_id)
    )
    manifest = _write_compare_shards(database.iter_compare_entries(compare_id), shards)
    _write_compare_assets(assets, manifest, summary)
    (output / "compare_report.html").write_text(_compare_html(summary), encoding="utf-8")


def _write_compare_shards(rows: Iterator[Any], directory: Path) -> list[dict[str, str]]:
    """按比较状态写入本地脚本分片，筛选时只加载一种状态。"""

    manifest: list[dict[str, str]] = []
    handles: dict[str, Any] = {}
    try:
        for row in rows:
            status = CompareStatus(row["status"])
            key = status.value
            if key not in handles:
                filename = f"{len(manifest):02d}-{key.lower()}.js"
                manifest.append({"key": key, "label": key, "file": f"shards/{filename}"})
                handle = (directory / filename).open("w", encoding="utf-8", newline="")
                handle.write(
                    "window.DiskHtmlCompare.registerShard("
                    + json.dumps(key, ensure_ascii=False)
                    + ",["
                )
                handles[key] = [handle, True]
            handle, first = handles[key]
            if not first:
                handle.write(",")
            handle.write(json.dumps(_row_to_dict(row), ensure_ascii=False, separators=(",", ":")))
            handles[key][1] = False
    finally:
        for handle, _ in handles.values():
            handle.write("]);\n")
            handle.close()
    return manifest


def _write_compare_assets(
    assets: Path, manifest: list[dict[str, str]], summary: dict[str, Any]
) -> None:
    """写入完全本地化的样式、清单和筛选脚本。"""

    (assets / "styles.css").write_text(
        "body{font:14px system-ui;margin:2rem;color:#1d2939;max-width:1200px}button{margin:.2rem;padding:.4rem .7rem;cursor:pointer}"
        "input{width:min(100%,42rem);padding:.5rem}table{border-collapse:collapse;width:100%;margin-top:1rem}"
        "td,th{border:1px solid #d0d5dd;padding:.4rem;text-align:left;vertical-align:top}tr{cursor:pointer}.muted{color:#667085}"
        "#detail{white-space:pre-wrap;background:#f9fafb;padding:1rem;overflow:auto}",
        encoding="utf-8",
    )
    (assets / "manifest.js").write_text(
        "window.DiskHtmlCompareManifest="
        + json.dumps(
            {"shards": manifest, "summary": summary}, ensure_ascii=False, separators=(",", ":")
        )
        + ";\n",
        encoding="utf-8",
    )
    (assets / "app.js").write_text(_compare_app_script(), encoding="utf-8")


def _compare_app_script() -> str:
    """返回可被 file:// 直接载入的比较报告交互脚本。"""

    return """window.DiskHtmlCompare={cache:{},registerShard:function(key,rows){this.cache[key]=rows;}};
(function(){
const m=window.DiskHtmlCompareManifest,list=document.querySelector('#statuses'),status=document.querySelector('#status'),tbody=document.querySelector('#entries tbody'),filter=document.querySelector('#filter'),detail=document.querySelector('#detail');let current=[];
document.querySelector('#summary').textContent=Object.entries(m.summary.statistics).map(([k,v])=>k+' '+v).join('，');
function describe(entry){detail.textContent=JSON.stringify({路径:entry.relative_path,状态:entry.status,旧大小:entry.old_size_bytes,新大小:entry.new_size_bytes,旧SHA256:entry.old_sha256,新SHA256:entry.new_sha256,错误:entry.error_message},null,2)}
function show(rows){tbody.replaceChildren();for(const entry of rows){const tr=document.createElement('tr');tr.onclick=()=>describe(entry);for(const value of [entry.relative_path,entry.status,entry.old_size_bytes??'',entry.new_size_bytes??'',entry.error_message||'']){const td=document.createElement('td');td.textContent=value;tr.append(td)}tbody.append(tr)}status.textContent='当前显示 '+rows.length+' 条比较结果'}
function apply(){const needle=filter.value.trim().toLocaleLowerCase();show(needle?current.filter(entry=>(entry.relative_path+' '+entry.status+' '+(entry.error_message||'')).toLocaleLowerCase().includes(needle)):current)}
filter.oninput=apply;
function select(rows){current=rows;filter.value='';show(rows)}
for(const shard of m.shards){const button=document.createElement('button');button.type='button';button.textContent=shard.label;button.onclick=()=>{if(window.DiskHtmlCompare.cache[shard.key]){select(window.DiskHtmlCompare.cache[shard.key]);return}const element=document.createElement('script');element.src='compare_assets/'+shard.file;element.onload=()=>select(window.DiskHtmlCompare.cache[shard.key]||[]);element.onerror=()=>status.textContent='无法加载本地分片：'+shard.file;document.head.append(element)};list.append(button)}
})();"""


def _compare_html(summary: dict[str, Any]) -> str:
    """生成比较报告的固定入口页。"""

    title = html.escape(f"DiskHTML 比较报告 {summary['compare']['id']}")
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><link rel="stylesheet" href="compare_assets/styles.css"></head><body><h1>{title}</h1><p id="summary"></p><h2>状态筛选</h2><div id="statuses"></div><p id="status" class="muted">选择一种状态加载比较结果。</p><input id="filter" type="search" placeholder="按路径、状态或错误信息筛选当前状态"><table id="entries"><thead><tr><th>路径</th><th>状态</th><th>旧大小</th><th>新大小</th><th>错误</th></tr></thead><tbody></tbody></table><h2>比较详情</h2><pre id="detail" class="muted">选择结果查看详情。</pre><script src="compare_assets/manifest.js"></script><script src="compare_assets/app.js"></script></body></html>"""

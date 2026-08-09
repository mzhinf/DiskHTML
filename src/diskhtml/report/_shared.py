"""报告导出器共用的文件写入与目录发布工具。"""

from __future__ import annotations

import csv
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterator[Any]) -> None:
    """以 UTF-8 BOM 流式写入 CSV，并忽略字段列表之外的数据。"""

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})


def write_json(path: Path, value: Any) -> None:
    """以 UTF-8 写入稳定缩进并带末尾换行的 JSON。"""

    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def row_to_dict(row: Any) -> dict[str, Any] | None:
    """把数据库行转换为 JSON 可序列化字典，并保留空值语义。"""

    return dict(row) if row is not None else None


def publish_directory(temporary: Path, destination: Path) -> None:
    """在 Windows 短暂占用目录时有限重试原子发布。"""

    for attempt in range(3):
        try:
            os.replace(temporary, destination)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.05 * (attempt + 1))

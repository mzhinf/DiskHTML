# DiskHTML

DiskHTML 是面向 Windows 10/11 的文件 Hash 冷备份校验工具。项目以 SQLite 保存长期权威索引，
始终计算 SHA256，并计划提供断点续扫、离线报告和历史快照比较。

## 当前状态

当前已实现工程骨架、数据库持久化、可靠扫描与断点恢复，以及离线报告导出。报告从完成快照流式输出
CSV/JSON，以原子目录发布；设计为可通过 `file://` 打开，并以本地分片按顶级目录懒加载，提供目录树、
当前分片搜索筛选和文件详情。实际 `file://` 浏览器直开仍待本机人工验收；比较引擎和图形界面按 `task_plan.md` 分阶段实现。

## 开发环境

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

## 命令行

```powershell
diskhtml --help
diskhtml init-db .\archive.sqlite3
diskhtml check-db .\archive.sqlite3
```

配置格式、数据格式、数据库迁移和恢复语义分别见 `config.example.toml`、`docs/data-format.md`、
`docs/database-migration.md` 和 `docs/recovery.md`。

# DiskHTML

DiskHTML 是面向 Windows 10/11 的文件 Hash 冷备份校验工具。项目以 SQLite 保存长期权威索引，
始终计算 SHA256，并计划提供断点续扫、离线报告和历史快照比较。

## 当前状态

当前已完成工程骨架、数据契约以及 SQLite 持久化与迁移。数据库支持版本化升级、批量事务、
流式仓储查询与比较任务记录；扫描、导出、完整比较引擎和图形界面仍按 `task_plan.md` 分阶段实现。

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

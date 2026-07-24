# DiskHTML

DiskHTML 是面向 Windows 10/11 的文件 Hash 冷备份校验工具。项目以 SQLite 保存长期权威索引，
始终计算 SHA256，并计划提供断点续扫、离线报告和历史快照比较。

## 当前状态

当前完成工程骨架与数据契约。`init-db` 和 `check-db` 用于验证命令行入口及数据库迁移框架；
扫描、导出、比较和图形界面仍按 `task_plan.md` 分阶段实现。

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

配置格式、数据格式和恢复语义分别见 `config.example.toml`、`docs/data-format.md` 和
`docs/recovery.md`。

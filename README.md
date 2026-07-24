# DiskHTML

DiskHTML 是面向 Windows 10/11 的文件 Hash 冷备份校验工具。项目以 SQLite 保存长期权威索引，
始终计算 SHA256，并计划提供断点续扫、离线报告和历史快照比较。

## 当前状态

当前已实现工程骨架、数据库持久化、可靠扫描与断点恢复、离线报告导出，以及历史/实时路径的流式比较。
比较服务以 SHA256 为最终依据，输出 CSV 与按状态懒加载的离线比较报告；两类报告的实际 `file://` 浏览器直开
仍待本机人工验收。CLI 命令与图形界面按 `task_plan.md` 分阶段实现。

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
diskhtml check-project .\archive.sqlite3
```

配置格式、数据格式、数据库迁移、恢复语义和 CLI 操作分别见 `config.example.toml`、`docs/data-format.md`、
`docs/database-migration.md`、`docs/recovery.md`、`docs/cli-guide.md`、`docs/benchmark.md`、`docs/user-guide.md` 和 `docs/release-checklist.md`。
## Windows 发布构建

图形界面发布包的构建命令、产物位置和发布前验证步骤见 [Windows 构建说明](docs/windows-build.md)。

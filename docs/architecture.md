# DiskHTML 架构说明

## 产品边界

DiskHTML 包含两个明确分离的界面：

- `DiskHTML.exe` 是生成器，只选择输入、执行扫描并生成 HTML/SQLite，不展示最终目录树或比对结果。
- 离线 HTML 是浏览器，负责目录树、面包屑、搜索、排序、详情、状态颜色、盘符切换、中文/英文切换和导出当前视图。

浏览器不能直接枚举任意本机目录，因此“历史快照目录与本机目录比较”必须由 EXE 协调。

## 入口与模块架构表

| 入口或模块 | 职责 | 主要依赖/被谁调用 |
|---|---|---|
| `scripts/gui_entry.py` | PyInstaller 发布入口；无参数进入桌面 UI，有参数进入 EXE CLI | `ui`、`exe_cli` |
| `src/diskhtml/_exe_config.py` | 从 `_internal/config` 定位模板，首次启动生成并保留 EXE 同目录默认配置 | `gui_entry`、PyInstaller 运行时 |
| `src/diskhtml/__main__.py` | `python -m diskhtml` 的高级 CLI 入口 | `cli` |
| `src/diskhtml/ui.py` | 基于 `tkinter/ttk` 的三任务桌面界面、字段校验、后台线程、运行状态与中英文切换 | Python 标准库、`ui_text`、`html_archive`、`scanner`、`config` |
| `src/diskhtml/ui_text.py` | 桌面界面中英文文案、当前语言状态与兼容常量访问 | `ui` |
| `src/diskhtml/version.py` | 从唯一产品版本源或安装元数据读取运行时版本 | `__init__`、UI、CLI、HTML 服务 |
| `src/diskhtml/exe_cli.py` | EXE 的 `snapshot`、`compare-source`、`render-sqlite` 命令 | `html_archive`、`config` |
| `src/diskhtml/cli.py` | 高级 SQLite 项目、恢复、校验和兼容导出命令 | `scanner`、`compare`、`database`、`report` |
| `src/diskhtml/_cli_options.py` | 两套 CLI 共享的扫描参数声明与配置合并 | `cli`、`exe_cli`、`config` |
| `src/diskhtml/html_archive.py` | 快照、SQLite 重渲染和“快照目录对本机目录”的应用服务 | `scanner`、`database`、`compare`、`archive_ui` |
| `src/diskhtml/archive_ui.py` | 内联 HTML/CSS/JavaScript、目录树、Lucide SVG 与浏览器端中英文渲染 | `html_archive`；不使用外部 CDN |
| `src/diskhtml/scanner.py` | 文件枚举、有界并发 Hash、单写入者、暂停和取消 | `database`、`disk`、`models`、`config` |
| `src/diskhtml/sampled_hash.py` | 固定次数、目标读取量的 SHA-256 大文件快速预检；不替代完整内容哈希 | Python 标准库；供预检调用方独立复用 |
| `src/diskhtml/disk.py` | 容量、卷 GUID、卷标、文件系统及可选物理磁盘元数据 | `scanner`；Win32 API + 可降级 PowerShell 查询 |
| `src/diskhtml/database.py` | SQLite 连接、迁移编排、事务、仓储和流式查询 | `models`、`util` |
| `src/diskhtml/_database_schema.py` | SQLite 模式声明、版本读写与结构校验 | `database` |
| `src/diskhtml/_project_check.py` | 项目完整性、枚举、引用与计数自检规则 | `database` |
| `src/diskhtml/_database_writes.py` | 逐条与批量入口共用的 SQL 写入与参数归一化 | `database` |
| `src/diskhtml/compare.py` | 按相对路径归并并产生完整一致、采样预检一致、已变化、新增、缺失或错误状态 | `database`、`scanner`、`models` |
| `src/diskhtml/_comparison_entries.py` | 从两个已排序文件行流生成比较条目的领域内部接口 | `compare`、`html_archive` |
| `src/diskhtml/models.py` | 领域枚举、进度、错误分类和状态转换契约 | 所有业务层 |
| `src/diskhtml/config.py` | 版本化 TOML 配置、默认值和校验 | UI、CLI、扫描器 |
| `src/diskhtml/report/exporter.py` | 高级 SQLite 扫描结果的 CSV/JSON/目录报告导出 | `cli`、基准脚本 |
| `src/diskhtml/report/_shared.py` | 报告导出器共用的 CSV、JSON 与目录发布工具 | 报告导出器 |
| `src/diskhtml/report/compare_exporter.py` | 高级比较结果导出 | `cli` |
| `src/diskhtml/logging_config.py` | 文本和结构化 JSON 日志 | `cli` |
| `src/diskhtml/util.py` | 时间、路径键和显示格式等底层工具 | 数据库、扫描、报告 |
| `scripts/project_metadata.py` | 读取 `pyproject.toml` 产品版本并生成 Windows EXE 版本资源 | 构建、发布验证、发布清单 |
| `scripts/build_windows.py` | 无 PowerShell 依赖的 PyInstaller onedir 构建、版本资源与 ZIP 打包 | 发布人员、CI |
| `scripts/build_windows.ps1` | 可选 PowerShell 薄包装，仅转发到 Python 构建器 | Windows 手工构建 |
| `scripts/verify_release.py` | 解压 ZIP，在隔离目录运行 EXE 并生成中文 HTML/SQLite | 发布人员、CI |
| `scripts/create_release_manifest.py` | 为目录式发布包生成文件 SHA-256 清单 | 发布流程 |
| `scripts/benchmark_scan.py` | 运行扫描与报告性能基准 | 性能测试 |
| `scripts/generate_stress_dataset.py` | 生成确定性压力数据集 | 性能测试 |

## 核心数据流表

| 工作流 | 输入 | 处理链 | 输出 |
|---|---|---|---|
| 生成目录快照 | 本机目录、扫描配置 | `ui/exe_cli → html_archive → scanner → database → archive_ui` | `名称_yy-mm-dd.html` + 同名 `.sqlite3` |
| 生成比对报告 | 基准 HTML、快照内目录、本机目录 | `ui/exe_cli → html_archive → scanner → compare → archive_ui` | 与快照同界面的比较 HTML，多一列状态 |
| 从 SQLite 生成 | 历史 `.sqlite3` | `ui/exe_cli → html_archive → database → archive_ui` | 当前模板版本 HTML，不重新扫描 |
| 高级兼容流程 | 项目 SQLite、扫描/比较命令 | `cli → scanner/compare/database → report` | 项目数据库、CSV/JSON/目录报告 |

## 数据与部署表

| 对象 | 规则 |
|---|---|
| HTML 快照 | 内嵌文件树、Hash、时间和卷信息；离线打开；不依赖 CDN |
| SQLite 索引 | 与快照 HTML 同名；用于恢复数据和重新生成新版 HTML |
| 比对状态 | `MATCH` 完整一致、`PRECHECK_MATCH` 采样预检一致、`CHANGED` 已变化、`ADDED` 本机新增、`MISSING` 基准存在但本机缺失、`ERROR` 无法可靠判断 |
| 路径键 | 保存原始相对路径与规范化 `path_key`；统一分隔符并 Unicode casefold |
| Hash 策略 | 默认计算 `full-sha256`；创建快照时可选择固定目标读取量、固定次数的采样策略，目标量内文件仍计算完整 SHA-256 |
| 采样指纹 | 写入 `sha256` 摘要列并由 `hash_algorithm` 明确标识，仅用于大文件快速预检，不作为完整内容一致性证明 |
| 产品版本 | 唯一来源为 `pyproject.toml` 的 `project.version`；HTML 使用 `generator` 记录生成版本，EXE 写入 Windows 文件版本资源 |
| EXE 发布 | PyInstaller `onedir`；发布 ZIP 内只有完整 `DiskHTML/` 顶层目录；不能单独复制 EXE |
| EXE 默认配置 | `_internal/config/config.example.toml` 是只读模板；首次启动生成同目录 `config.toml`，已有文件不覆盖；GUI 和 EXE CLI 默认读取 |
| PowerShell | 不参与构建核心；运行时仅用于补充物理磁盘型号、序列号和分区，失败时降级记录 |

## 依赖边界

1. UI 不直接读写 SQLite 表，只调用应用服务。
2. 扫描器是 SQLite 的单写入者；Hash 工作者只读文件并通过有界队列返回结果。
3. `archive_ui` 只渲染传入数据，不扫描本机目录。
4. 比较以相对路径为准，不依赖历史与当前目录具有相同盘符或绝对路径。
5. HTML 模板升级不得修改已有 SQLite 数据语义；格式变更必须同步 `data-format.md` 和迁移文档。
6. 默认 EXE 不暴露高级项目数据库 UI；兼容能力仅保留在 Python CLI。

## 架构决策

| 编号 | 决策 | 原因 |
|---|---|---|
| ADR-001 | HTML 是默认用户交付物，SQLite 是同名索引 | 用户需要可直接打开、传递和归档的可视化结果 |
| ADR-002 | 目录比较由 EXE 协调 | 浏览器安全模型禁止离线页面枚举任意本机目录 |
| ADR-003 | 有界并发 + SQLite 单写入者 | 控制内存并避免数据库写竞争 |
| ADR-004 | 默认完整 SHA-256，显式允许采样预检 | 在保留完整一致结论的同时，为大文件提供可控 HDD 寻道成本的快速预检 |
| ADR-008 | 当前 HTML/SQLite 不兼容旧格式且数据库版本保持 3 | 本次直接更新数据契约，不维护迁移分支；缺字段时明确要求重新生成 |
| ADR-005 | 路径比较键版本化 | 支持大小写、Unicode 和未来兼容演进 |
| ADR-006 | 发布采用 onedir + ZIP | Python 与 Tcl/Tk 运行时需要随启动器完整分发，目录包也便于反向审计和独立验证 |
| ADR-007 | 构建核心使用 Python | PyInstaller 本身是 Python 工具，避免把 PowerShell 变成不必要的构建前置条件 |

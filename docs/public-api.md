# 公共 API 与兼容边界

## 目的

本页定义 DiskHTML 1.x 重构期间必须保持稳定的用户入口、Python 集成入口、数据契约和兼容名称。未列入本页的下划线私有名称可以在保持外部行为的前提下重构。

## 用户入口

| 入口 | 当前行为 | 稳定要求 |
|---|---|---|
| `diskhtml` | 高级 CLI，包含 HTML、SQLite 项目、恢复、校验和导出命令 | 命令名、参数、默认值、输出方向和退出码保持稳定 |
| `python -m diskhtml` | 与 `diskhtml` 使用同一高级 CLI | 与安装脚本入口等价 |
| `diskhtml-gui` | 启动三任务 Tkinter 桌面界面 | 入口名称和无参数启动行为保持稳定 |
| `DiskHTML.exe` 无参数 | 启动桌面界面 | 不因内部模块拆分改变 |
| `DiskHTML.exe` 有参数 | 进入精简 EXE CLI | 只保留 `snapshot`、`render-sqlite`、`compare-source` |

高级 CLI 当前命令为：`init-db`、`check-db`、`check-project`、`scan`、`snapshot`、`render-sqlite`、`compare-source`、`compare-html`、`resume`、`status`、`export`、`compare`、`verify`、`import`。

## 显式 Python 导出

### 包根

- `diskhtml.__version__`

### 采样指纹

`diskhtml.sampled_hash` 的显式导出为：

- `FULL_SHA256_ALGORITHM`
- `DEFAULT_SAMPLE_TARGET_BYTES`
- `DEFAULT_SAMPLE_COUNT`
- `MAX_SAMPLE_COUNT`
- `FileChangedDuringHashError`
- `SampledHashResult`
- `sampled_sha256`
- `sampled_sha256_algorithm`

### 报告

- `diskhtml.report.export_scan`
- `diskhtml.report.export_compare`

## 受支持的集成入口

以下入口虽然不从包根重导出，但被架构、测试或维护流程直接使用，1.x 行为保持型重构不得改变其导入路径和调用签名：

- 配置：`HashMode`、`ScanConfig`、`AppConfig`、`load_config`
- 数据库：`Database` 及其现有公开方法、`DatabaseBatch`
- 扫描：`Scanner`、`ScanController`、`ScanOptions`
- HTML 应用服务：`create_html_snapshot`、`render_html_snapshot_from_sqlite`、`compare_html_archives`、`compare_html_directory_to_source`、`html_snapshot_scan_config`、`html_snapshot_directories`、`read_html_snapshot`
- 领域状态：`SourceType`、`ScanStatus`、`HashStatus`、`CompareStatus`、`ErrorCode`、`ScanProgress`、`validate_scan_transition`

`ScanJob`、`VolumeInfo`、`FileRecord`、`CompareResult`、`ErrorRecord` 当前没有仓库内调用方，但名称公开。确认弃用策略前继续保留，不能在普通死代码清理中删除。

## 兼容名称与命令

- `ScanOptions` 必须继续是 `ScanConfig` 的同一对象别名。
- `ui_text` 的动态常量访问继续按当前语言返回文案。
- `compare-html` 与高级 SQLite CLI 属于兼容入口，除非独立迁移任务明确安排弃用，否则不得删除。
- `Database` 的逐条写方法与 `Database.batch()` 的批量写方法具有不同事务时机，重构时都应保留。

## 数据与状态契约

- 配置格式版本：1。
- HTML 快照格式版本：2。
- SQLite 模式版本：3。
- 默认 Hash 策略：`full-sha256`。
- 完整一致状态：`MATCH`；采样预检一致状态：`PRECHECK_MATCH`。
- 旧 HTML 或旧 SQLite 不自动升级，格式不符时明确拒绝。

## 变更规则

下列变化必须单独立项，不能混入行为保持型重构：

- 删除、重命名或移动本页列出的入口；
- 改变参数、默认值、返回类型、输出方向或退出码；
- 改变 HTML/SQLite/config 格式版本或兼容策略；
- 删除兼容别名、命令或数据库写入入口。

需要调整时，先更新本页和用户文档，提供弃用周期、迁移说明与主版本策略，再实施代码变化。

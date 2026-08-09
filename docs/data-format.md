# 数据与兼容格式

## 版本策略

- 配置文件使用整数 `format_version`，当前为 `1`；未知版本直接拒绝。
- SQLite 在 `schema_meta.schema_version` 保存模式版本，当前仍为整数 `3`；本次不执行数据库升级，缺少当前字段的既有版本直接拒绝并要求重新生成。
- 单文件 HTML 格式版本为整数 `2`；旧 HTML 不兼容，必须由当前版本重新生成。
- 扫描任务保存创建时的配置快照，恢复时不得套用新的默认配置。
- 当前发布不承诺读取此前数据库或 HTML；格式字段、算法标识和记录列必须同时匹配。

## 时间格式

所有持久化时间使用 UTC ISO 8601，例如 `2026-07-24T08:30:00.000000Z`。界面可以转换为
本地时区，但数据库和导出数据不保存含糊的本地时间。

## 路径格式

- `relative_path` 使用 `/` 分隔并保留原始大小写。
- `path_key` 版本 1 使用 `/` 分隔后执行 Unicode `casefold`。
- 绝对源路径只用于定位扫描目标，不参与不同快照的内容一致性判断。
- 同一扫描出现相同 `path_key` 时必须报 `PATH_COLLISION`，不得覆盖另一条路径。

## Hash 与可信状态

- `sha256` 在 `hash_status = OK` 时必须存在；其语义由同记录的 `hash_algorithm` 明确区分。
- `full-sha256` 表示完整 SHA-256；`sampled-sha256-<目标读取量MB>_<次数>` 表示仅供快速预检的采样指纹。
- `sha512` 可为空，且不能代替 SHA256。
- `UNSTABLE` 表示 Hash 前后元数据变化；`ERROR` 表示无法读取。
- 缺少可信 Hash 或算法标识的文件在比较时只能得到 `ERROR`，不能得到一致状态。

## 日志格式

默认文本日志字段依次为时间、级别、记录器和中文消息。启用 JSON 后，每行是一个对象，
稳定字段为 `timestamp`、`level`、`logger`、`message`，异常时增加 `exception`。

## 报告导出格式

- 报告格式版本为 `1`，写入 `summary.json.format_version`；导出只接受状态为 `COMPLETED` 的扫描快照。
- 根目录包含 `disk_info.json`、`summary.json`、带 UTF-8 BOM 的 `file_list.csv` 与 `hash_list.csv`，以及固定入口 `report.html`。
- `report_assets/manifest.js` 只保存统计和分片清单；文件明细位于 `report_assets/shards/*.js`，按相对路径的顶级目录分片。
- 浏览器选择一个分片后，才通过本地 `<script>` 标签载入该分片并在内存构建该分片的目录树；首屏不嵌入全量文件。
- 所有样式、脚本和分片均为相对本地资源，不使用 CDN、`fetch` 或网络服务，因此可由 `file://` 直接打开。
- 导出先写入目标同级的隐藏临时目录，全部写入成功后使用原子改名发布；目标目录已存在时拒绝覆盖。

## 比较导出格式

- 比较任务保存左侧旧来源和右侧新来源；比较条目按规范化 `path_key` 流式归并，结果显示右侧路径。
- 大小、算法和摘要都相同且算法为 `full-sha256` 时为 `MATCH`；采样算法相同时为 `PRECHECK_MATCH`；任一比较字段不同为 `CHANGED`。
- 任一侧的摘要状态不是 `OK` 或 SHA256 缺失时必须输出 `ERROR`，不能判为 `MATCH`。
- 完成比较可导出 `compare_summary.json`、UTF-8 BOM 的 `compare_entries.csv` 和 `compare_report.html`。
- `compare_assets/manifest.js` 仅含统计和状态分片清单，明细按 `MATCH`、`PRECHECK_MATCH`、`CHANGED`、`ADDED`、`MISSING`、`ERROR` 分片并由本地脚本按需加载。

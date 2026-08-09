# 数据库迁移与写入边界

## 模式版本

项目数据库在 `schema_meta.schema_version` 保存整数模式版本，当前版本仍为 `3`。本次 Hash 策略变更不提升版本号，也不提供旧库升级路径。

- 新数据库从版本 0 依次执行所有迁移。
- 只有新建数据库或字段完整的当前版本数据库可以打开。
- 低于、高于当前版本，或虽标记为版本 3 但缺少算法字段的数据库都会被明确拒绝；用户需重新生成。
- `migration_history` 记录从版本 2 开始的迁移时间，用于诊断导入问题。

## 事务语义

`Database.batch()` 开启 `BEGIN IMMEDIATE` 事务。一个批次中的文件、目录、卷、错误、进度和
比较记录要么全部提交，要么在异常时全部回滚。扫描编排层应由一个写入线程独占批量写入器；
Hash 工作线程只产生待写入结果。

单条 `record_file`、`record_directory` 等方法为兼容调用方保留，但每次都会独立提交。大量扫描
必须使用批量写入器，避免每个文件一次 SQLite 事务。

## 导入已有项目

`Database.open_existing()` 只接受已经存在且符合当前字段契约的 SQLite 文件，并在打开时执行版本和必要字段校验，不升级旧数据库。
导入失败不会创建替代数据库，也不会降级模式。

## 索引

- `files(scan_id, hash_status)`：断点续扫筛选。
- `files(scan_id, path_key, size_bytes, sha256)`：路径对齐与内容比较。
- `directories(scan_id, parent_path_key)`：目录树和分片报告。
- `scan_errors(scan_id, relative_path)`：错误追踪。
- `compare_entries(compare_id, status, relative_path)`：比较报告筛选与流式导出。

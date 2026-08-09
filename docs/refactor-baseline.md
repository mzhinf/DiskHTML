# 现代化重构行为基线

## 基线范围

本基线用于证明 `docs/refactor-plan.md` 中的结构调整没有改变用户行为。基线随本页列出的自动测试共同维护，运行环境为 Python 3.12 和 Windows。

## 自动质量基线

| 项目 | 当前结果 | 命令或证据 |
|---|---|---|
| Ruff 静态检查 | 通过 | `python -m ruff check src tests scripts` |
| 完整测试 | 当前套件全部通过 | `python -m unittest discover -s tests -p "test_*.py"` |
| 文档索引与链接 | 通过 | `tests/test_documentation.py` |
| UTF-8 与说明规则 | 通过 | `tests/test_source_encoding.py` |
| 差异空白检查 | 通过 | `git diff --check` |

GitHub Windows CI 当前只执行格式、Ruff 和完整测试。Windows onedir 构建、许可证生成与解压后发布包验证由受控本地发布流程执行。

## 自动 parity 契约

`tests/test_refactor_baseline.py` 固定以下行为：

- 包根、采样指纹和报告模块的显式导出；
- 目标采样读取量的新名称以及 1.x 旧名称兼容入口；
- `ScanOptions` 兼容别名与公开领域名称；
- 两套 CLI 的命令集合和固定宽度帮助输出；
- 配置、HTML、SQLite 版本与领域状态枚举；
- SQLite 表、列和索引的语义结构；
- 包含中文、特殊字符、空文件和采样大文件的 HTML/SQLite 快照语义。

CLI 帮助快照位于 `tests/fixtures/refactor_baseline/`。帮助宽度固定为 80 列，避免终端宽度造成无意义差异。

## 非确定字段的比较规则

以下字段由运行环境或执行时间生成，等价检查前必须规范化：

- UUID、扫描和比较任务 ID；
- UTC 创建、更新时间和完成时间；
- 临时目录绝对路径和盘符；
- 扫描速率、预计剩余时间和测试耗时；
- SQLite 自动生成的行 ID。

路径、状态、摘要、具体 Hash 算法、文件大小、目录层级、错误码、schema 列和索引不得被规范化掉。

## 已有可靠性覆盖

| 行为 | 现有测试 |
|---|---|
| 暂停、继续、取消和恢复 | `test_scan_recovery.py` |
| 读取期间变化、权限错误和源路径缺失 | `test_scan_recovery.py` |
| Windows 长路径与 junction | `test_scanner.py`、`test_scan_recovery.py` |
| 完整与采样 Hash 边界 | `test_sampled_hash.py`、`test_scanner.py` |
| 六种比较状态与目录聚合 | `test_compare.py`、`test_html_archive.py` |
| SQLite 事务回滚和 1 万条批量写入 | `test_database.py` |
| CLI、EXE CLI 与打包入口 | `test_cli.py`、`test_exe_cli.py`、`test_gui_entry.py` |
| Tk 表单、任务和固定窗口余量 | `test_ui.py` |

## 人工与视觉基线

在修改 `ui.py` 前，必须保存并确认三任务页的中文/英文、采样控件、最坏错误信息、运行区和结果区截图。在修改离线 HTML 资源或交互前，必须从 `file://` 打开实际报告并验证：

1. 目录树展开和折叠；
2. 面包屑导航；
3. 搜索与排序；
4. 文件详情；
5. 中文/英文切换；
6. Windows 盘符切换；
7. CSV 导出；
8. 完整一致、采样预检一致和真实差异颜色。

视觉基线只证明“当前界面应保持不变”，不授权新增或调整 UI。任何 UI 功能变化仍需独立原型确认。

# DiskHTML 文档索引

本页是仓库文档表。新增、删除、重命名文档或改变功能边界时，必须同步更新此表。

## 文档表

| 文档 | 包含的信息 | 主要读者 | 需要更新的时机 |
|---|---|---|---|
| [README.md](../README.md) | 项目定位、主要功能、快速使用、开发命令、限制和许可状态 | 所有人 | 功能、入口、发布方式或依赖改变 |
| [README.en.md](../README.en.md) | README 的英文版本，含桌面语言切换说明 | 英文用户、海外贡献者 | README 功能、入口、发布方式或界面语言支持改变 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 开发环境、代码说明规则、测试和提交要求 | 贡献者 | 工具链或质量门禁改变 |
| [SECURITY.md](../SECURITY.md) | 支持版本和漏洞报告方式 | 用户、维护者 | 支持策略或报告渠道改变 |
| [CHANGELOG.md](../CHANGELOG.md) | 未发布变更和版本历史 | 用户、发布人员 | 每次面向用户的变更和发布 |
| [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) | Tkinter/Tcl-Tk、Lucide 与最终发布组件的许可机制 | 维护者、发布人员 | 增删第三方依赖、运行时或素材 |
| [architecture.md](architecture.md) | 系统入口、模块职责、依赖边界、数据流和架构决策 | 开发者、维护者 | 模块边界、数据流或部署改变 |
| [benchmark.md](benchmark.md) | 扫描和报告性能基准、指标与压力数据集 | 性能测试、发布人员 | 性能实现或基准方法改变 |
| [cli-guide.md](cli-guide.md) | 默认 HTML 工作流和高级 SQLite CLI | 高级用户、开发者 | 命令、参数或输出改变 |
| [data-format.md](data-format.md) | 格式版本、时间、路径、Hash、日志和导出契约 | 开发者 | 持久化或交换格式改变 |
| [database-migration.md](database-migration.md) | SQLite schema、迁移、事务、导入和索引 | 维护者 | 数据库版本或迁移逻辑改变 |
| [diskhtml-exe-guide.md](diskhtml-exe-guide.md) | EXE 启动、三个任务、命令行、状态和软链接 | Windows 用户 | 桌面流程或 EXE 命令改变 |
| [html-archive-design.md](html-archive-design.md) | 产品边界、分层、比较语义和可视化要求 | 设计、开发者 | HTML 数据或交互设计改变 |
| [html-ui-guide.md](html-ui-guide.md) | 离线页面的目录树、搜索、排序、详情和盘符切换 | 最终用户 | HTML 页面交互改变 |
| [recovery.md](recovery.md) | 扫描状态、暂停、取消和恢复语义 | 开发者 | 扫描状态机改变 |
| [refactor-plan.md](refactor-plan.md) | 行为保持型现代化重构批次、等价检查和独立迁移边界 | 维护者、贡献者 | 完成重构批次、发现新技术债或调整迁移边界 |
| [sampled-fingerprint.md](sampled-fingerprint.md) | 固定次数、固定预算采样指纹的接口、格式和安全边界 | 开发者 | 采样算法、参数、返回字段或格式版本改变 |
| [release-checklist.md](release-checklist.md) | 许可、质量、构建、独立运行和人工验收门禁 | 发布人员 | 发布流程或验收标准改变 |
| [release-licenses.md](release-licenses.md) | 发布许可证目录、组件识别、来源优先级和自动阻断规则 | 发布人员、维护者 | 运行时、构建方式或许可证来源改变 |
| [rework-analysis.md](rework-analysis.md) | 多轮返工根因、PowerShell 边界、防线和剩余技术债 | 维护者、贡献者 | 发生重大返工或验收策略改变 |
| [user-guide.md](user-guide.md) | 普通用户端到端流程、保存迁移和页面浏览 | 最终用户 | 用户流程或术语改变 |
| [windows-build.md](windows-build.md) | Python 构建入口、目录包结构和发布验收 | 构建、发布人员 | 构建工具或产物布局改变 |

## 仓库结构表

| 路径 | 内容 | 是否进入发布 ZIP |
|---|---|---:|
| `src/diskhtml/` | 应用、扫描、数据库、比较和 HTML 渲染源码 | 是（由 PyInstaller 打包） |
| `scripts/` | 构建、发布验证、基准和维护脚本 | 否 |
| `tests/` | 单元、集成、编码和构建契约测试 | 否 |
| `docs/` | 用户、架构、数据和发布文档 | 否 |
| `.github/workflows/` | GitHub Windows CI | 否 |
| `build/` | 本地构建、发布 ZIP 和验证产物 | 否，且被 Git 忽略 |
| `.venv/` | 项目 Python 环境 | 否，且被 Git 忽略 |

## GitHub 发布整理表

| 项目 | 当前状态 | 证据或后续动作 |
|---|---|---|
| 源码、测试、脚本均有文件级用途说明 | 已完成 | `tests/test_source_encoding.py` 自动检查 |
| UTF-8、LF/CRLF 和生成物忽略规则 | 已完成 | `.editorconfig`、`.gitattributes`、`.gitignore` |
| 文档索引与架构表 | 已完成 | 本文和 `architecture.md` |
| Windows CI 与独立发布包验证 | 已完成 | `.github/workflows/ci.yml`、`scripts/verify_release.py` |
| 旧式项目 UI 发布说明清理 | 已完成 | `release-checklist.md` 已按三个任务页重写 |
| 发布许可证材料 | 已自动化 | 根据最终目录包生成声明与许可证，并以未知组件、版本或 Qt 残留为构建阻断项；见 `release-licenses.md` |
| GitHub remote、默认分支和版本标签 | 待仓库创建后完成 | 建议确认分支命名，并按 `pyproject.toml` 的 `project.version` 创建对应 `v<版本>` 标签 |
| Git 提交者邮箱隐私 | 待维护者确认 | 当前历史会公开提交者邮箱；必要时改用 GitHub noreply 或重写历史 |

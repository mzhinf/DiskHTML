# 任务计划：文件列表图标与 GitHub 发布前清理

## 目标

在不改变扫描、Hash、SQLite、比对和 HTML 数据格式的前提下，为右侧文件列表的 Name 列加入离线 SVG 文件类型图标，清理确认无效或重复的代码与仓库噪声，并完成完整测试、Windows 构建和本地 Git 提交。

### Phase 1：仓库审计

**Status:** complete

- 检查跟踪文件、构建产物、临时目录、硬编码路径和常见敏感信息。
- 确认可安全移除的重复信号、包装函数和测试断言。

### Phase 2：SVG 与代码清理

**Status:** complete

- 在文件列表 Name 前加入指定的文件夹与文件 SVG。
- 修复无搜索状态覆盖图标节点的问题。
- 移除确认无效代码并维护项目定位文案。

### Phase 3：GitHub 仓库维护

**Status:** complete

- 增加 UTF-8、换行和二进制文件约定。
- 忽略测试临时目录、本地数据库与环境变量文件。
- 保持 `名称_yy-mm-dd` 默认命名规则不变。

### Phase 4：发布级验证

**Status:** complete

- Ruff 静态检查、格式检查和源码编码检查通过。
- 完整 66 项测试通过。
- 真实 HTML 脚本检查、PowerShell 7 构建和 EXE 产物验收通过。

### Phase 5：提交与交付

**Status:** complete

- 审查最终差异和敏感信息。
- 提交本地 Git；不在未授权情况下推送到 GitHub。

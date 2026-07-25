# 任务计划：目录式 EXE 发布包与目录树 Lucide 图标

## 目标

明确 DiskHTML 使用 PyInstaller 目录式 EXE 发布，自动把 `DiskHTML.exe` 与 `_internal` 打成可分发 ZIP，避免只复制启动器导致 Python DLL 缺失；同时用指定 Lucide SVG 表示左侧目录树的关闭和打开状态。

### Phase 1：打包诊断

**Status:** complete

- 检查 PyInstaller 参数、发布目录和现有 EXE 依赖。
- 确认截图错误来自只复制 onedir 启动器而遗漏 `_internal`。

### Phase 2：目录式 EXE 发布包

**Status:** complete

- 构建脚本显式使用 `--onedir`。
- 自动生成包含完整 `DiskHTML` 目录的 ZIP。
- 保持双击 GUI 和命令行子命令入口不变。

### Phase 3：目录树 SVG

**Status:** complete

- 使用指定的 folder 与 folder-open Lucide 路径。
- 根据目录展开状态切换图标，不引入外部资源。

### Phase 4：验证

**Status:** complete

- 更新测试并运行完整回归。
- 解压 ZIP 后在独立目录运行 EXE，验证 HTML 与 SQLite 生成。

### Phase 5：提交

**Status:** complete

- 审查差异、记录 ZIP/EXE 哈希并提交 Git。

## Errors Encountered

| 错误 | 尝试 | 处理 |
|---|---:|---|
| 图片查看工具受 Windows 分离沙箱限制，无法重新读取附件 | 1 | 使用用户消息中已显示的错误内容继续诊断，不重复调用 |
| PowerShell 语法检查命令中的 `[ref]` 变量未预先声明 | 1 | 改为先声明 `$tokens` 与 `$errors`，再调用解析器 |

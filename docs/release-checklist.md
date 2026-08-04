# 发布检查清单

本清单只适用于当前三个生成任务和 onedir ZIP 发布方式。所有必选项完成并保留证据后，才能发布二进制。

## 法务与仓库

- [x] 根目录存在维护者确认的 MIT `LICENSE`，构建时复制为发布根目录 `LICENSE.txt`。
- [ ] `THIRD_PARTY_NOTICES.md` 与实际使用的依赖、Lucide SVG 一致。
- [ ] 确认 Git 历史中的提交者邮箱可公开。
- [ ] 版本号、`CHANGELOG.md` 和发布说明已更新。
- [ ] 工作区除本次发布修改外干净，无 `.env`、数据库、HTML、日志、IDE 配置或构建目录被跟踪。

## 代码与文档

- [ ] 所有自有 Python、PowerShell 和工作流文件包含文件级用途说明。
- [ ] `docs/README.md` 已列出每份文档，`docs/architecture.md` 与模块和数据流一致。
- [ ] README、用户指南、EXE 指南和 CLI 指南使用当前命令与三个任务名称。
- [ ] 没有“冷备功能”“打开报告页”“扫描配置页”“新建项目”等已移除界面的过时描述。

## 自动质量门禁

~~~powershell
.\.venv\Scripts\python.exe -m ruff format --check src scripts tests
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
git diff --check
~~~

- [ ] 上述命令全部通过，并记录测试数量与时间。
- [ ] 编码测试确认所有代码为严格 UTF-8、无损坏问号和非必要中文 `\u` 转义。
- [ ] HTML 行为测试覆盖快照、ADDED、MISSING、CHANGED、搜索精确性、排序、目录跳转和 SVG。

## 构建与发布包

~~~powershell
.\.venv\Scripts\python.exe .\scripts\build_windows.py --clean
.\.venv\Scripts\python.exe .\scripts\verify_release.py .\build\release\DiskHTML-win-x64.zip
.\.venv\Scripts\python.exe .\scripts\create_release_manifest.py .\build\dist\DiskHTML .\build\DiskHTML-release-manifest.json
Get-FileHash .\build\dist\DiskHTML\DiskHTML.exe -Algorithm SHA256
Get-FileHash .\build\release\DiskHTML-win-x64.zip -Algorithm SHA256
~~~

- [ ] ZIP 只有一个 `DiskHTML/` 顶层目录，并包含 `DiskHTML.exe` 与 `_internal/python3*.dll`。
- [ ] 独立解压验证实际生成含中文数据的 HTML 和同名 SQLite。
- [ ] 发布页面和下载说明明确“完整解压 ZIP，不能单独复制 EXE”。
- [ ] 记录 Python、PyInstaller、Tcl/Tk、Windows 版本、文件大小和 SHA-256。

## Windows 人工验收

- [ ] “生成目录快照”自动建议 `名称_yy-mm-dd.html`，并生成同名 SQLite。
- [ ] “生成比对报告”可选择基准 HTML、快照内任意目录、本机目录和输出 HTML。
- [ ] “从 SQLite 生成”不重新扫描即可生成新 HTML。
- [ ] 运行状态只在任务开始后显示，暂停、继续、取消有效。
- [ ] 完成区显示完整路径，“打开 HTML”和“打开所在文件夹”有效。
- [ ] HTML 的目录树、面包屑、搜索、高亮、排序、详情、SHA-256、导出和盘符切换有效。
- [ ] 比对报告显示 `MATCH/CHANGED/ADDED/MISSING/ERROR`，差异颜色和父目录标记正确。
- [ ] Windows 10 与 Windows 11 上均完成一次 ZIP 解压后的验收。

## 发布归档

- [ ] 归档 ZIP、目录清单、SHA-256、变更说明、测试结果和人工验收记录。
- [ ] 创建与版本号一致的 Git 标签和 GitHub Release。
- [ ] 保留上一个稳定 ZIP 与数据库格式说明，确保可回退。

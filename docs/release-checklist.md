# 发布检查清单

本清单用于 Windows 图形界面发布。所有项目均完成并留下证据后，才可标记为可发布。

## 代码与质量

- [ ] 当前工作区干净，版本号和变更说明已更新。
- [ ] 使用项目虚拟环境运行 Ruff 格式检查和静态检查。
- [ ] 完整单元测试通过，并记录测试数量与执行时间。
- [ ] 运行“check-db”和“check-project”验证用于验收的项目数据库。
- [ ] 已保存性能基准原始 JSON；HDD、SSD 与压力数据集的参数和介质信息可追溯。

~~~powershell
.\.venv\Scripts\python.exe -m ruff format --check src scripts tests
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m diskhtml check-project .\archive.sqlite3
~~~

## 打包

- [ ] 安装打包依赖。
- [ ] 使用干净构建目录生成图形界面发布包。
- [ ] 记录生成的可执行文件路径、大小、SHA256 和构建环境。
- [ ] 确认 build 目录不纳入 Git。

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
.\scripts\build_windows.ps1 -Clean
Get-FileHash .\build\dist\DiskHTML\DiskHTML.exe -Algorithm SHA256
.\.venv\Scripts\python.exe scripts\create_release_manifest.py .\build\dist\DiskHTML .\build\DiskHTML-release-manifest.json
~~~

## Windows 10/11 人工验收

在未安装 Python 和项目开发依赖的干净 Windows 10、Windows 11 环境中，分别执行以下流程：

- [ ] 启动 DiskHTML.exe，创建新项目后关闭并重新打开。
- [ ] 扫描含普通文件、中文路径和单个文件的样本。
- [ ] 验证进度、暂停、取消、错误列表，以及取消后的恢复。
- [ ] 比较两个快照，并比较当前目录与历史快照。
- [ ] 导出扫描和比较报告，在浏览器中以 file:// 直接打开并确认筛选、目录树和详情可用。
- [ ] 重启程序后检查扫描任务、比较结果和项目自校验仍可用。
- [ ] 记录任何 Defender、权限、文件锁或长路径提示，并确认不会造成静默数据遗漏。

## 发布归档

- [ ] 归档发布包、SHA256、版本说明、测试结果、基准 JSON 和已验收的项目副本。
- [ ] 保留上一个稳定版本及其数据库格式说明，确保可回退。
- [ ] 未完成任一跨环境人工验收项时，不得声明发布包已完成验收。

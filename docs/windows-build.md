# Windows 构建与验收

## 构建

建议使用 PowerShell 7.4 或更高版本执行构建。DiskHTML 运行时会优先调用 `pwsh.exe` 获取磁盘信息；未安装 PowerShell 7 时会兼容回退到 Windows PowerShell 5.1。

在项目虚拟环境中安装构建依赖：

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
pwsh.exe -NoLogo -NoProfile -File .\scripts\build_windows.ps1
~~~

脚本显式使用 PyInstaller `onedir` 模式，EXE 位于 `build\dist\DiskHTML\DiskHTML.exe`，完整发布包位于 `build\release\DiskHTML-win-x64.zip`。运行时不需要安装 Python，但 `DiskHTML.exe` 必须与同目录的 `_internal` 一起保留；推荐直接分发 ZIP。

无参数时启动 HTML 快照 GUI；带参数时运行精简命令行入口，例如：

~~~cmd
DiskHTML.exe snapshot F:\Documents .\资料快照.html
~~~

## EXE 验收

在未安装 Python 的 Windows 10/11 环境中：

1. 将 `build\release\DiskHTML-win-x64.zip` 解压到一个空目录，确认其中同时存在 `DiskHTML\DiskHTML.exe` 和 `DiskHTML\_internal`。
2. 双击解压后的 EXE，确认“生成目录快照”“生成比对报告”“从 SQLite 生成”三个任务页可切换；不要只复制 EXE。
3. 对含中文路径的小目录生成新的 HTML 快照并用浏览器打开。
4. 在历史 HTML 树中选择一个目录，并与本机目录生成 HTML 比较报告。
5. 在命令提示符执行 `DiskHTML.exe snapshot <目录> <新.html>`，确认 HTML 实际生成。
6. 确认输出目录同时包含用户选择的 HTML 文件和同名 `.sqlite3` 快照索引；用该索引重新生成新版 HTML。
7. 扫描期间测试暂停、继续或取消操作。

构建前应通过：

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
~~~

详细操作见 [DiskHTML.exe 使用指南](diskhtml-exe-guide.md)。

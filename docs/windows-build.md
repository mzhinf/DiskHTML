# Windows 构建与验收

## 构建

在项目虚拟环境中安装构建依赖：

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
.\scripts\build_windows.ps1
~~~

产物位于 build\dist\DiskHTML\DiskHTML.exe。无参数时启动 HTML 冷备 GUI；带参数时运行精简命令行入口，例如：

~~~cmd
DiskHTML.exe backup F:\Documents .\资料冷备.html
~~~

## EXE 验收

在未安装 Python 的 Windows 10/11 环境中：

1. 启动 DiskHTML.exe，确认工具栏只显示“生成冷备 HTML、比较冷备目录、打开报告、扫描配置、暂停、继续、取消”。
2. 对小目录生成新的 HTML 冷备并用浏览器打开。
3. 在历史 HTML 树中选择一个目录，并与本机目录生成 HTML 比较报告。
4. 确认比较报告状态筛选可见。
5. 在命令提示符执行 DiskHTML.exe backup <目录> <新.html>，确认 HTML 实际生成。
6. 确认输出目录只包含用户选择的 HTML 文件，不需要 SQLite 项目文件。
7. 扫描期间测试暂停、继续或取消操作。

构建前应通过：

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
~~~

详细操作见 [DiskHTML.exe 使用指南](diskhtml-exe-guide.md)。
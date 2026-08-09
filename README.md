# DiskHTML

[中文](README.md) | [English](README.en.md)

DiskHTML 是面向 Windows 10/11 的目录快照与 Hash 预检/比对工具。默认使用完整 SHA-256，也可为大文件选择固定预算、固定次数的采样预检；采样结果不是完整内容一致性证明。

## 主要功能

- 生成目录快照：输出单个可视化 HTML，并同时保存同名 SQLite 索引。
- 生成比对报告：选择历史 HTML 中的任意目录，与本机任意目录比较。
- 从 SQLite 生成：不重新扫描源目录，使用历史索引生成当前版本 HTML。
- 记录 Name、Size、Modified、Created、摘要、具体算法、卷信息和可选物理磁盘信息。
- HTML 不使用外部 CDN，双击即可离线浏览、搜索、排序、导出当前视图，并可在页面右上角切换中文或英文。
- 桌面界面支持中英文切换；在状态栏右侧选择语言，切换时保留已输入的路径和选项。

## Windows 使用

发布物是便携式目录包，而不是可单独复制的单文件 EXE。请下载并完整解压 `DiskHTML-win-x64.zip`，然后运行：

~~~text
DiskHTML\DiskHTML.exe
DiskHTML\_internal\...
~~~

`DiskHTML.exe` 和 `_internal` 必须保持在同一目录。只复制 EXE 会出现 `Failed to load Python DLL`。

桌面界面包含三个任务页：

1. “生成目录快照”：选择源目录和输出 HTML。
2. “生成比对报告”：选择基准快照、快照内目录、待检查目录和输出报告；当前目录自动使用 HTML 指定算法。
3. “从 SQLite 生成”：选择 `.sqlite3` 索引和新的 HTML 路径。

命令行示例：

~~~cmd
DiskHTML.exe snapshot F:\Documents .\资料快照.html
DiskHTML.exe compare-source .\资料快照.html 资料\照片 E:\当前照片 .\照片比较.html
DiskHTML.exe render-sqlite .\资料快照.sqlite3 .\资料快照-新版.html
~~~

完整步骤见 [DiskHTML.exe 使用指南](docs/diskhtml-exe-guide.md)和[用户指南](docs/user-guide.md)。

## 开发与测试

项目要求 Python 3.12，并固定使用项目 `.venv`：

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
.\.venv\Scripts\python.exe -m ruff format --check src scripts tests
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
~~~

构建不要求 PowerShell：

~~~powershell
.\.venv\Scripts\python.exe .\scripts\build_windows.py --clean
.\.venv\Scripts\python.exe .\scripts\verify_release.py .\build\release\DiskHTML-win-x64.zip
~~~

`scripts/build_windows.ps1` 仅是兼容习惯用法的可选包装。详细说明见 [Windows 构建与验收](docs/windows-build.md)。

## 文档

[文档索引](docs/README.md)列出了每份文档的内容、读者和维护时机；[架构说明](docs/architecture.md)列出了入口、模块职责、依赖边界和三条核心数据流。

## 已知边界

- 浏览器安全模型不允许离线 HTML 直接扫描任意本机目录，因此比对扫描由 EXE 完成。
- 物理磁盘型号、序列号和分区信息目前通过可降级的 PowerShell 查询采集；查询失败不会阻止扫描、Hash、HTML 或 SQLite 生成。
- 当前发布形态是 PyInstaller `onedir` 目录包加 ZIP，不是 `onefile` 单文件程序。

## 许可状态

DiskHTML 使用 [MIT License](LICENSE)。构建流程会根据最终目录包自动生成 Python、Tcl/Tk、PyInstaller、Lucide 和实际原生组件的英文声明及完整许可证文本；详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 [docs/release-licenses.md](docs/release-licenses.md)。

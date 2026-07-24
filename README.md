# DiskHTML

DiskHTML 是面向 Windows 10/11 的文件 Hash 冷备校验工具。默认交付物是可离线打开、带可展开层级文件树、可搜索和可比较的单个 HTML 文件，使用方式接近 Snap2HTML。

Windows 用户可直接使用 DiskHTML.exe：

~~~cmd
DiskHTML.exe backup F:\Documents .\资料冷备.html
DiskHTML.exe compare-source .\资料冷备.html 资料\照片 E:\当前照片 .\照片比较.html
~~~

DiskHTML.exe 读取 HTML 冷备的文件树，让用户选择历史目录后与本机任意目录比较。扫描期间 SQLite 仅作为临时可靠索引，成功后自动清理，不是用户交付物。

完整操作见 [用户指南](docs/user-guide.md)、[DiskHTML.exe 使用指南](docs/diskhtml-exe-guide.md)和[HTML 冷备与目录比较设计](docs/html-archive-design.md)。

## 开发环境

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
~~~
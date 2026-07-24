# DiskHTML

DiskHTML 是面向 Windows 10/11 的文件 Hash 冷备校验工具。默认交付物是可离线打开、可搜索和可比较的单个 HTML 文件，使用方式接近 Snap2HTML。

~~~powershell
diskhtml backup D:\资料 .\资料冷备.html
diskhtml compare-html .\旧副本.html .\新副本.html .\副本比较.html
~~~

冷备 HTML 展示文件清单、SHA256、Hash 错误和统计；比较 HTML 提供 MATCH、CHANGED、ADDED、MISSING、ERROR 的可视化筛选。扫描期间 SQLite 仅作为临时可靠索引，成功后自动清理，不是用户交付物。

完整操作见 [用户指南](docs/user-guide.md)，架构决策见 [HTML 冷备设计](docs/html-archive-design.md)。

## 开发环境

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
~~~

SQLite 项目命令仍保留给高级的中断恢复、既有项目维护和旧式目录报告导出。
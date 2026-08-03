# CLI 操作手册

所有开发态命令使用项目 `.venv`：

~~~powershell
.\.venv\Scripts\python.exe -m diskhtml --help
~~~

发布 ZIP 中的 `DiskHTML.exe` 支持同名的三个默认命令。

## 默认工作流：HTML 快照和目录比较

扫描目录并生成可视化 HTML 与同名 SQLite：

~~~powershell
.\.venv\Scripts\python.exe -m diskhtml snapshot D:\资料 .\资料快照.html --workers 2 --queue-size 32 --chunk-size 4194304 --sha512
~~~

将历史 HTML 中的目录与本机目录比较：

~~~powershell
.\.venv\Scripts\python.exe -m diskhtml compare-source .\资料快照.html 资料\照片 E:\当前照片 .\照片比较.html
~~~

比较快照根目录时，第二个位置参数使用 `.`。输出 HTML 必须不存在。

从 SQLite 重建当前版本 HTML：

~~~powershell
.\.venv\Scripts\python.exe -m diskhtml render-sqlite .\资料快照.sqlite3 .\资料快照-新版.html
~~~

`compare-html` 仅保留为旧自动化脚本的兼容命令；默认 EXE 不提供两份 HTML 比较入口。EXE 操作见 [DiskHTML.exe 使用指南](diskhtml-exe-guide.md)。

## 高级 SQLite 项目工作流

以下命令保留用于中断恢复、既有项目维护和旧式目录报告：

~~~powershell
.\.venv\Scripts\python.exe -m diskhtml scan .\archive.sqlite3 D:\资料
.\.venv\Scripts\python.exe -m diskhtml status .\archive.sqlite3
.\.venv\Scripts\python.exe -m diskhtml resume .\archive.sqlite3 <扫描标识>
.\.venv\Scripts\python.exe -m diskhtml compare .\archive.sqlite3 D:\旧副本 E:\新副本
.\.venv\Scripts\python.exe -m diskhtml verify .\archive.sqlite3 <历史扫描标识> E:\当前副本
~~~

旧式目录报告导出：

~~~powershell
.\.venv\Scripts\python.exe -m diskhtml export .\archive.sqlite3 <扫描标识> .\扫描报告
.\.venv\Scripts\python.exe -m diskhtml export .\archive.sqlite3 <比较标识> .\比较报告 --compare
~~~

高级项目完整性检查和导入：

~~~powershell
.\.venv\Scripts\python.exe -m diskhtml check-db .\archive.sqlite3
.\.venv\Scripts\python.exe -m diskhtml check-project .\archive.sqlite3
.\.venv\Scripts\python.exe -m diskhtml import .\新项目.sqlite3 .\已有项目.sqlite3
~~~

参数或运行错误会输出中文说明并返回非零退出码。
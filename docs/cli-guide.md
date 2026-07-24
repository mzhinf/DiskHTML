# CLI 操作手册

所有命令均使用项目虚拟环境中的解释器：

~~~powershell
.\.venv\Scripts\python.exe -m diskhtml --help
~~~

## 默认工作流：HTML 冷备和目录比较

扫描目录或单个文件，并直接生成一个可视化 HTML 冷备：

~~~powershell
.\.venv\Scripts\python.exe -m diskhtml backup D:\资料 .\资料冷备.html --workers 2 --queue-size 32 --chunk-size 4194304 --sha512
~~~

从历史冷备 HTML 的文件树选择一个目录，并将其和本机目录比较：

~~~powershell
.\.venv\Scripts\python.exe -m diskhtml compare-source .\资料冷备.html 资料\照片 E:\当前照片 .\照片比较.html
~~~

若比较冷备根目录，第二个位置参数使用 `.`。输出 HTML 必须不存在。冷备和比较报告都可用浏览器离线打开，提供统计、筛选、分页和条目详情。扫描临时使用 SQLite，但完成后自动清理；用户不需要保存数据库。

`compare-html` 仍保留为兼容旧自动化脚本的高级命令；DiskHTML.exe 的默认界面和命令不提供该入口。EXE 的完整操作见 [DiskHTML.exe 使用指南](diskhtml-exe-guide.md)。

## 高级 SQLite 项目工作流

以下命令保留用于中断恢复、既有项目维护及旧式目录报告：

~~~powershell
.\.venv\Scripts\python.exe -m diskhtml scan .\archive.sqlite3 D:\资料
.\.venv\Scripts\python.exe -m diskhtml status .\archive.sqlite3
.\.venv\Scripts\python.exe -m diskhtml resume .\archive.sqlite3 <扫描标识>
.\.venv\Scripts\python.exe -m diskhtml compare .\archive.sqlite3 D:\旧副本 E:\新副本
.\.venv\Scripts\python.exe -m diskhtml verify .\archive.sqlite3 <历史扫描标识> E:\当前副本
~~~

旧式目录报告的导出命令如下：

~~~powershell
.\.venv\Scripts\python.exe -m diskhtml export .\archive.sqlite3 <扫描标识> .\扫描报告
.\.venv\Scripts\python.exe -m diskhtml export .\archive.sqlite3 <比较标识> .\比较报告 --compare
~~~

高级项目还支持完整性检查和导入：

~~~powershell
.\.venv\Scripts\python.exe -m diskhtml check-db .\archive.sqlite3
.\.venv\Scripts\python.exe -m diskhtml check-project .\archive.sqlite3
.\.venv\Scripts\python.exe -m diskhtml import .\新项目.sqlite3 .\已有项目.sqlite3
~~~

所有参数错误与运行错误均以中文输出，并以非零退出码结束。
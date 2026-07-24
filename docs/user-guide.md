# 用户操作手册

## 准备

项目使用 Python 3.12 及项目虚拟环境。开发或命令行使用时，先安装依赖：

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
~~~

图形界面可通过以下命令启动：

~~~powershell
diskhtml-gui
~~~

每个项目对应一个 SQLite 数据库。请将数据库与被校验的数据分开存放，并定期复制数据库文件作为项目元数据备份。

## 新建、打开与自检项目

在图形界面中使用“新建项目”选择新的数据库路径，或用“打开项目”选择已有数据库。命令行可执行：

~~~powershell
diskhtml init-db .\archive.sqlite3
diskhtml check-db .\archive.sqlite3
diskhtml check-project .\archive.sqlite3
~~~

“check-db”验证 SQLite 文件完整性；“check-project”还会检查模式版本、迁移记录、引用关系、状态值和扫描进度计数。任何检查失败时都不应继续把该项目作为唯一恢复依据，应先保留副本并排查问题。

## 扫描与恢复

图形界面支持选择目录或单个文件，加载 TOML 扫描配置，并显示已发现文件数、已 Hash 字节数、吞吐、预计剩余时间和当前路径。扫描中可暂停或取消；已完整提交的文件结果会保留。

命令行等价操作如下：

~~~powershell
diskhtml scan .\archive.sqlite3 D:\资料 --workers 2 --queue-size 32
diskhtml status .\archive.sqlite3
diskhtml resume .\archive.sqlite3 <扫描标识>
~~~

恢复只复用大小和纳秒修改时间均未变化、且 Hash 状态为 OK 的记录。权限不足、文件消失或扫描中发生变化都会被记录为错误，而不是静默跳过。恢复前应确认原始源路径仍可访问。

## 比较和复验

可在图形界面中比较两个已完成快照，也可将当前目录与一个已完成快照比较。命令行可直接比较两个当前路径，或复验当前副本：

~~~powershell
diskhtml compare .\archive.sqlite3 D:\旧副本 E:\新副本
diskhtml verify .\archive.sqlite3 <历史扫描标识> E:\当前副本
~~~

比较以 SHA256 为最终依据。MATCH 表示两侧均有可信且相同的 SHA256；任何一侧 Hash 错误、Hash 不稳定或摘要缺失都会显示为 ERROR。

## 导出离线报告

只允许导出已完成扫描或已完成比较。导出目标目录必须不存在，程序不会覆盖已有目录。

~~~powershell
diskhtml export .\archive.sqlite3 <扫描标识> .\扫描报告
diskhtml export .\archive.sqlite3 <比较标识> .\比较报告 --compare
~~~

扫描报告入口是“扫描报告\report.html”，比较报告入口是“比较报告\compare_report.html”。报告不依赖网络，应用会在写入完成后以原子目录发布；Windows 短暂文件锁会有限重试。请直接用浏览器打开本地文件，并保留完整报告目录，不要仅移动 HTML 文件。

## 导入与备份

可将已存在项目数据库导入新路径：

~~~powershell
diskhtml import .\新项目.sqlite3 .\已有项目.sqlite3
~~~

导入源和目标不得相同。发布或迁移前应先复制源数据库，在副本上执行导入及“check-project”，并保留原始数据库直至人工验收结束。

更多格式与恢复细节见“数据格式说明”“数据库迁移说明”“恢复说明”和“性能基准”文档。

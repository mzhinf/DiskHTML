# 用户指南

## Windows 图形界面

普通用户完整解压发布 ZIP 后运行 `DiskHTML\DiskHTML.exe`。程序窗口只生成报告，不在窗口内展示目录树或比对结果。

三个任务分别是：

- “生成目录快照”：扫描本机目录并生成 HTML + SQLite；
- “生成比对报告”：将历史 HTML 中的目录与当前本机目录比较；
- “从 SQLite 生成”：不重新扫描，生成当前模板版本的 HTML。

## 日常使用：生成 HTML 快照

选择源目录后，程序默认建议 `目录名_yy-mm-dd.html`，并在相同位置生成同名 `.sqlite3`。例如在 2026-07-26 扫描 `资料`，建议输出为 `资料_26-07-26.html` 和 `资料_26-07-26.sqlite3`。

HTML 类似桌面文件浏览器，可离线查看目录树、文件列表、大小、时间和 SHA-256；SQLite 保留完整扫描数据，可在页面升级后重新生成 HTML。

命令行也可使用：

~~~powershell
DiskHTML.exe snapshot D:\资料 .\资料快照.html
~~~

输出必须是不存在的 `.html`；同名 SQLite 也不能已存在。程序拒绝覆盖，以避免误删历史结果。

## 从 HTML 快照目录比较本机目录

打开“生成比对报告”页：

1. 选择以前生成的基准 HTML；
2. 点击“选择快照内目录”，选择根目录或任意子目录；
3. 选择当前待检查的本机目录；
4. 生成新的比对 HTML。

历史目录会重定根，因此两侧绝对路径、盘符和根目录名可以不同。报告状态为 `MATCH`、`CHANGED`、`ADDED`、`MISSING` 和 `ERROR`；详细含义见 [DiskHTML.exe 使用指南](diskhtml-exe-guide.md)。

## 从 SQLite 重新生成

在“从 SQLite 生成”页选择快照同名 `.sqlite3` 和新的 HTML 路径。该过程读取保存的数据，不重新访问或 Hash 原目录。

## 保存和迁移

建议一起保存同名 `.html` 和 `.sqlite3`：

- HTML 内含完整可视化界面和快照数据，可直接发送或离线打开；
- SQLite 用于重新生成新界面，并保留更适合程序读取的结构化记录。

移动硬盘盘符改变时，可在 HTML 详情区域选择新盘符，让本机文件链接跟随变化。链接是否可打开仍受浏览器对 `file:///` 的安全策略和当前文件是否存在影响。

超大目录会产生较大的单文件 HTML，浏览器打开时会占用相应内存；建议使用现代 64 位浏览器，并避免同时打开多个超大快照。

## 高级 SQLite 项目工作流

以下命令只用于维护已有项目、断点恢复和旧式目录报告，不属于桌面程序的三个日常任务：

~~~powershell
.\.venv\Scripts\python.exe -m diskhtml init-db .\archive.sqlite3
.\.venv\Scripts\python.exe -m diskhtml scan .\archive.sqlite3 D:\资料
.\.venv\Scripts\python.exe -m diskhtml resume .\archive.sqlite3 <扫描标识>
~~~

## 离线快照页面

目录树、搜索高亮、排序、详情列、导出当前视图和盘符切换见[离线快照页面使用指南](html-ui-guide.md)。
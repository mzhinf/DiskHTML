# 用户指南

## 日常使用：生成 HTML 冷备

冷备的交付物是一个可直接双击打开的 HTML 文件，类似 Snap2HTML。扫描期间会使用临时 SQLite 索引来保证 Hash、排序和错误记录可靠；成功后临时索引会自动清理，不会出现在冷备目录中。

~~~powershell
diskhtml backup D:\资料 .\资料冷备.html
~~~

也可以扫描单个文件：

~~~powershell
diskhtml backup D:\资料\重要文件.zip .\重要文件冷备.html
~~~

可用选项：

~~~powershell
diskhtml backup D:\资料 .\资料冷备.html --workers 2 --queue-size 32 --sha512
~~~

输出文件必须是一个不存在的 .html 文件。程序拒绝覆盖已有冷备，以避免误删历史快照。

完成后直接用浏览器打开 HTML。页面显示文件和目录数量、已完成 Hash 数、问题数；可按路径、状态或错误信息筛选，单击条目查看 SHA256、时间和错误详情。列表每次只渲染部分行，可继续点击“显示更多”。

## 比较两个冷备

先分别生成旧副本和新副本的 HTML 冷备，再执行比较：

~~~powershell
diskhtml compare-html .\旧副本.html .\新副本.html .\副本比较.html
~~~

比较结果也是单个 HTML，可直接发送或归档。报告可按以下状态筛选：

- MATCH：两侧 SHA256 都有效且相同；
- CHANGED：路径相同但 SHA256 不同；
- ADDED：仅存在于新快照；
- MISSING：仅存在于旧快照；
- ERROR：任一侧 Hash 不可用、读取失败或扫描期间不稳定，不能作为一致性依据。

左侧始终视为旧快照，右侧视为新快照。

## 保存和迁移

请保留完整的 .html 文件本身，不需要附带 SQLite 或网络资源。HTML 内含可视化界面和快照数据，复制到其他 Windows 电脑后仍可离线打开和比较。

单文件 HTML 会包含完整文件清单。超大目录的快照可能较大，浏览器打开时会占用相应内存；这种情况下建议使用现代 64 位浏览器，并避免同时打开多个超大快照。

## 图形界面和高级项目

图形界面的“打开报告”可打开任意冷备或比较 HTML。现有 SQLite 项目工作流仍保留给需要中断恢复、检查既有项目或导出旧式目录报告的高级场景：

~~~powershell
diskhtml init-db .\archive.sqlite3
diskhtml scan .\archive.sqlite3 D:\资料
diskhtml resume .\archive.sqlite3 <扫描标识>
~~~

日常冷备和比较不需要使用这些命令。

## 开发环境

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
~~~
# 用户指南

## Windows 图形界面

普通用户可直接运行 DiskHTML.exe。界面提供“生成冷备 HTML、比较冷备目录、打开报告、扫描配置”和扫描控制按钮；不需要创建、打开或管理 SQLite 项目。

比较工作流是：先选择历史 HTML 冷备，再在其文件树中选择一个目录，最后选择本机任意目录。具体点击步骤、状态定义和命令行方式见 [DiskHTML.exe 使用指南](diskhtml-exe-guide.md)。

## 日常使用：生成 HTML 冷备

每次冷备会生成一个可直接双击打开的 HTML 文件和一个同名 SQLite 索引，例如 `资料冷备.html` 与 `资料冷备.sqlite3`。HTML 类似 Snap2HTML，用于离线浏览；SQLite 保留可靠的扫描、Hash、排序和错误记录，可在页面升级后重新生成 HTML，而不必重新扫描。

~~~powershell
diskhtml backup D:\资料 .\资料冷备.html
~~~

也可以扫描单个文件：

~~~powershell
diskhtml backup D:\资料\重要文件.zip .\重要文件冷备.html
~~~

输出文件必须是一个不存在的 .html 文件。程序拒绝覆盖已有冷备，以避免误删历史快照。

完成后直接用浏览器打开 HTML。页面左侧是可展开的层级文件树，单击目录可筛选右侧文件；右侧显示文件和目录数量、已完成 Hash 数、问题数，并可按路径、状态或错误信息搜索。每个文件都保存并显示 SHA-256，单击条目可查看时间和错误详情。

## 从 HTML 冷备目录比较本机目录

在 DiskHTML.exe 中选择“比较冷备目录”，从历史 HTML 的文件树选择目录后，再选择本机目录。历史目录会重定根，因此不要求历史路径和本机路径的绝对位置或目录名相同。

结果也是单个 HTML，可直接发送或归档。报告状态为 MATCH、CHANGED、ADDED、MISSING 和 ERROR；含义见 EXE 使用指南。

## 保存和迁移

请一起保留同名的 `.html` 和 `.sqlite3`：HTML 内含可视化界面和快照数据，复制到其他 Windows 电脑后仍可离线打开；SQLite 可由 DiskHTML.exe 或命令 `render-sqlite` 重新生成当前版本 HTML。

单文件 HTML 会包含完整文件清单。超大目录的快照可能较大，浏览器打开时会占用相应内存；这种情况下建议使用现代 64 位浏览器，并避免同时打开多个超大快照。

## 高级 SQLite 项目工作流

以下命令仅用于维护已有项目、断点恢复和旧式目录报告：

~~~powershell
diskhtml init-db .\archive.sqlite3
diskhtml scan .\archive.sqlite3 D:\资料
diskhtml resume .\archive.sqlite3 <扫描标识>
~~~

日常冷备和目录比较不需要使用这些命令。
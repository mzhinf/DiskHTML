# DiskHTML.exe 使用指南

## 启动

发布包的主程序是 build\dist\DiskHTML\DiskHTML.exe。双击运行即可，不需要安装 Python 或单独管理 SQLite。

无参数启动图形界面。界面提供：

- 生成冷备 HTML；
- 比较冷备目录；
- 从 SQLite 生成 HTML；
- 打开报告；
- 扫描配置；
- 暂停、继续、取消。

## 生成冷备 HTML

1. 点击“生成冷备 HTML”。
2. 选择需要冷备的目录。
3. 指定一个新的 .html 文件名和保存位置。
4. 等待状态栏显示“HTML 冷备已生成”。
5. 点击“打开报告”并选择刚生成的 HTML。

生成后会得到同名的 `.html` 和 `.sqlite3` 两个文件。HTML 是可直接浏览的离线页面，左侧提供可展开的层级文件树；单击目录即可筛选右侧文件清单。每个文件均显示 SHA-256、大小、修改时间、创建时间和错误信息。SQLite 是可再渲染的冷备索引，可用于生成以后版本的 HTML，而不必重新扫描原始目录。

## 在命令提示符生成冷备

重新构建后的 DiskHTML.exe 也支持 HTML 冷备命令。进入 EXE 所在目录后，在命令提示符中可执行：

~~~cmd
DiskHTML.exe backup F:\Documents .\资料冷备.html
~~~

在 PowerShell 中必须带当前路径前缀：

~~~powershell
.\DiskHTML.exe backup F:\Documents .\资料冷备.html
~~~

命令成功后会在当前目录生成 `资料冷备.html` 和 `资料冷备.sqlite3`。两者均不能已存在。

## 从 SQLite 重新生成 HTML

当页面布局升级时，不必重新扫描原目录。点击“从 SQLite 生成 HTML”，选择同名 `.sqlite3` 冷备索引并指定一个新的 `.html` 输出文件即可。

命令行也可使用：

~~~cmd
DiskHTML.exe render-sqlite .\资料冷备.sqlite3 .\资料冷备-新版.html
~~~
## 从冷备目录比较本机目录

1. 点击“比较冷备目录”。
2. 选择历史 HTML 冷备。
3. 在弹出的文件树中选择要比较的历史目录；“冷备根目录”表示整个快照。
4. 选择任意本机目录。
5. 指定新的 .html 比较报告。
6. 完成后用“打开报告”查看结果。

历史目录会被当作比较左侧根目录，本机目录被当作右侧根目录。两侧绝对路径不需要相同。

也可在命令提示符执行：

~~~cmd
DiskHTML.exe compare-source .\资料冷备.html 资料\照片 E:\当前照片 .\照片比较.html
~~~

若比较 HTML 冷备的根目录，第二个位置参数使用一个点：

~~~cmd
DiskHTML.exe compare-source .\资料冷备.html . E:\当前副本 .\根目录比较.html
~~~

比较报告状态含义：

- MATCH：两侧 SHA256 有效且相同；
- CHANGED：同一路径的 SHA256 不同；
- ADDED：仅存在于本机目录；
- MISSING：仅存在于历史目录；
- ERROR：摘要不可用或扫描记录存在问题，不能判定一致。

## 扫描配置和控制

“扫描配置”可加载 TOML 文件，设置工作线程数、队列、读取块、SHA512 和排除规则。加载后会应用到后续冷备和本机目录比较扫描。

暂停、继续和取消作用于当前运行中的扫描。取消的冷备或比较不会发布为完成结果；重新执行相应操作即可开始新任务。

## 已从 EXE 界面移除的功能

为保持默认流程清晰，EXE 不再提供：

- 新建或打开 SQLite 项目；
- 旧式扫描任务列表、恢复任务和错误列表；
- 基于 SQLite 项目快照的旧式比较；
- 两份 HTML 冷备的默认比较；
- CSV、JSON 和目录式报告导出。

这些兼容能力仍可由 Python 命令行维护旧项目，但不是 DiskHTML.exe 的用户工作流。
## 软链接与盘符切换

默认不跟随软链接和 Windows 重解析目录。如需将链接指向的文件写入冷备，在 `backup` 或 `compare-source` 后使用 `--follow-links`：

~~~cmd
DiskHTML.exe backup F:\Documents .\资料冷备.html --follow-links
~~~

程序会按实际目录身份防止链接循环。HTML 详情页提供“文件所在盘符”选择；当移动硬盘盘符变更时，可切换为新盘符查看对应本机路径。路径经过软链接时，由 Windows 按当前链接目标解析。

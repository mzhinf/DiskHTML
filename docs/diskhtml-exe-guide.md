# DiskHTML.exe 使用指南

## 启动

完整发布包是 `DiskHTML-win-x64.zip`。完整解压后运行 `DiskHTML\DiskHTML.exe`，不需要安装 Python。`DiskHTML.exe` 必须与旁边的 `_internal` 保持在同一目录；只复制 EXE 会出现 `Failed to load Python DLL`。

无参数启动固定大小的桌面生成界面。顶部有三个任务页：

- 生成目录快照；
- 生成比对报告；
- 从 SQLite 生成。

桌面程序不显示最终目录树或比对内容；任务完成后使用“打开 HTML”查看离线报告。

## 生成目录快照

1. 打开“生成目录快照”页。
2. 选择源目录。程序自动建议 `目录名_yy-mm-dd.html`。
3. 如有需要，更改输出位置并启用“跟随软链接和 Windows 重解析点”。
4. 点击“生成快照 HTML”。
5. 完成后会得到同名 `.html` 和 `.sqlite3`，并可打开 HTML 或所在文件夹。

HTML 是离线浏览页面；SQLite 是可再渲染索引。每个文件记录 Name、Size、Modified、Created 和 SHA-256，快照头部包含生成时间和可获取的磁盘信息。

命令提示符用法：

~~~cmd
DiskHTML.exe snapshot F:\Documents .\资料快照.html
~~~

PowerShell 中需要当前路径前缀：

~~~powershell
.\DiskHTML.exe snapshot F:\Documents .\资料快照.html
~~~

输出 HTML 和同名 SQLite 均不能已存在，程序不会覆盖历史结果。

## 生成比对报告

1. 打开“生成比对报告”页。
2. 在“基准快照”选择以前生成的 DiskHTML HTML。
3. 点击“选择快照内目录”；默认根目录，也可选择树中的任意子目录。
4. 在“待检查目录”选择当前需要检查的本机文件夹。
5. 确认输出报告位置，点击“生成比对 HTML”。

历史目录会重定为比较根，本机目录是当前根，两侧盘符、绝对路径和根目录名不需要相同。

~~~cmd
DiskHTML.exe compare-source .\资料快照.html 资料\照片 E:\当前照片 .\照片比较.html
DiskHTML.exe compare-source .\资料快照.html . E:\当前副本 .\根目录比较.html
~~~

状态含义：

| 状态 | 含义 |
|---|---|
| `MATCH` | 两侧存在同一路径，且有效 SHA-256 相同 |
| `CHANGED` | 同一路径的内容或受比较元数据不同 |
| `ADDED` | 仅存在于当前本机目录 |
| `MISSING` | 仅存在于基准快照 |
| `ERROR` | Hash 或扫描记录不足，无法可靠判断 |

比对 HTML 与普通快照使用相同目录树和详情表，仅增加状态列、状态颜色和差异目录标记。

## 从 SQLite 生成

1. 打开“从 SQLite 生成”页。
2. 选择生成快照时保留的 `.sqlite3`。
3. 指定一个不存在的新 HTML。
4. 点击“从 SQLite 生成 HTML”。

~~~cmd
DiskHTML.exe render-sqlite .\资料快照.sqlite3 .\资料快照-新版.html
~~~

此任务不重新读取或 Hash 原目录，适合页面模板升级后重新生成报告。

## 运行状态

任务开始后才显示运行区，包含当前阶段、路径、已扫描文件数、Hash 进度、总体进度和暂停/继续/取消。取消不会把未完成结果伪装为成功。任务完成后显示输出完整路径和打开按钮。

## 软链接与盘符切换

默认不跟随软链接和 Windows 重解析目录。需要时在桌面页勾选对应选项，或使用：

~~~cmd
DiskHTML.exe snapshot F:\Documents .\资料快照.html --follow-links
~~~

程序按实际目录身份防止链接循环。HTML 详情提供盘符选择；移动硬盘盘符改变后，可切换到新盘符生成可由浏览器打开的 `file:///` 链接。

## 不属于默认 EXE 的功能

新建/打开 SQLite 项目、旧式任务表、恢复列表、两份 HTML 默认比较、CSV/JSON/目录式报告和扫描配置页不在桌面程序中。这些兼容能力只保留在 Python 高级 CLI，避免干扰三个日常任务。
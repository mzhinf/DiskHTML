# 进度记录

## 2026-07-25：快照命名与目录树样式

- 快照默认 HTML 文件名已调整为 `源目录_yy-mm-dd.html`；与之对应的 SQLite 索引自动使用同名 `源目录_yy-mm-dd.sqlite3`。
- HTML 快照摘要新增本地时区的生成时间，格式为 `yyyy-mm-dd hh:mm`。
- 目录树已改为细虚线层级、绘制的黄色文件夹图标、轻量方框 `+ / -` 控件与浅蓝选中行。
- 针对本次修改运行 11 项 HTML 与桌面界面回归测试，全部通过。
- 已通过离线 JavaScript 语法校验并重新构建 `build\dist\DiskHTML\DiskHTML.exe`。

## 2026-07-25：目录树组件重构

- 已移除目录树对原生 `details/summary` 的依赖，改为显式树节点、展开按钮、标签按钮和子节点容器。
- 树形几何统一为 18px 层级缩进、13px 展开框、24px 行高和 16px 文件夹图标。

- 11 项 HTML/桌面界面回归测试通过，全项目 Ruff 检查通过，离线 JavaScript 语法检查通过。
- 新版 EXE 已生成真实样本 `reworked.html` 和 `reworked.sqlite3`；样本包含显式树节点和展开按钮，不包含旧的 `createElement('details')`。


## 2026-07-25 中文编码修复

- 恢复 57 处真实损坏的中文文本。
- 新增 `tests/test_source_encoding.py`，检查源码严格 UTF-8 解码和字符串损坏标记。
- `.venv\Scripts\python.exe -m ruff check src tests`：通过。
- `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`：63 项通过。
- 重建 `build/dist/DiskHTML/DiskHTML.exe` 成功。
- 实测 `DiskHTML.exe snapshot --help`：中文“跟随软链接和 Windows 重解析点”完整，未出现连续问号或 Unicode 替换字符。


## 2026-07-25 PowerShell 7 与 UTF-8 源码维护

- 确认系统 PowerShell 7 版本为 7.6.4，当前工具宿主仍为 Windows PowerShell 5.1。
- 磁盘信息采集改为优先解析 `pwsh.exe`，未安装时回退 `powershell.exe`。
- 将 HTML 模板、报告渲染、扫描器和测试中的可读中文 Unicode 转义改为直接 UTF-8。
- 保留脚本安全转义、CSV BOM 和编码回归检测所需的功能性转义。
- 新增 PowerShell 版本选择测试和可读文本转义回归测试。
- Ruff 静态检查通过，编码回归测试 3 项通过。
- 受限沙箱内执行磁盘 CIM 查询返回拒绝访问；后续使用普通 Windows 权限验证。

- PowerShell 7/5.1 实际磁盘查询均成功。
- Ruff 格式化与静态检查通过。
- 完整测试 66 项通过。

- 首次 PowerShell 7 构建因运行中的工作区 DiskHTML.exe 锁定发布目录而失败；确认路径后关闭该实例，重建成功。
- 新 EXE 命令行中文检查通过，未发现问号或 Unicode 替换字符。
- 新 EXE SHA-256：`6C510EDAEC041297D986962A84C6289B485BFDCC68A13497075BC7B784C405D0`。
- 最终代码扫描：可读中文 Unicode 转义 0 处，损坏问号文件 0 个。


## 2026-07-26 图标、磁盘信息与桌面 UI 调整

- 将快照头部文本符号替换为用户指定的 Lucide hard-drive 内联 SVG。
- 在快照头部增加磁盘信息行，显示硬盘型号、硬盘 ID、容量、盘符和文件系统；缺失字段会自动省略。
- 比对报告数据新增基准快照和当前目录两侧的磁盘记录，页面显示当前待检查目录所在硬盘信息。
- 桌面任务页签改为等宽分段导航，使用 Qt 内置目录、比较和硬盘图标，并强化选中与悬停状态。
- 主窗口固定为 900 × 650，快照内目录选择对话框保持可调整。
- 保持 `名称_yy-mm-dd.html` 和同名 SQLite 规则，并增加防回退测试。

- Ruff 静态检查通过；桌面 UI 与 HTML 快照针对性测试 11 项通过。
- 离屏界面截图已成功生成到 `build/ui-preview.png`；首次写入 `C:\tmp` 失败，改用项目构建目录。
- 当前图片查看工具受 Windows 分离沙箱限制无法读取预览图，因此以 Qt 尺寸、图标与样式自动化断言继续验收。

- 完整格式检查、静态检查和 66 项测试全部通过。
- 首次构建因运行中的工作区 DiskHTML.exe 锁定发布目录失败；确认并关闭该实例后，PowerShell 7 重建成功。
- EXE 临时中文文件名验收被外层 PowerShell 5.1 转换成非法问号路径；改用 ASCII 临时名后验证通过，未修改程序逻辑。
- 新 EXE 实测记录硬盘型号 `INTEL SSDSCKKW256G8`、硬盘序列号、卷 GUID 和 255027310592 字节容量。
- 新 EXE 实测确认指定 SVG 和磁盘信息区域存在，旧文本图标已移除。

- 最终差异检查无错误，可读中文 Unicode 转义 0 处，损坏中文文件 0 个。
- 新 EXE SHA-256：`C839109150575C91DD2D5139C725E73E9B8B4F73DB2B4BB9987BAA358C3582C5`。

## 2026-07-26 文件列表 SVG 与仓库清理

- 文件列表 Name 前已加入用户指定的文件夹和文件 Lucide SVG，显示尺寸固定为 16px，颜色由 CSS 继承并区分目录与文件。
- 修复无搜索状态下文本赋值覆盖图标节点的问题，移除旧 Emoji 和方框占位符。
- 移除拖放路径的重复信号链、HTML 渲染无逻辑转发函数和重复测试断言。
- 新增 `.editorconfig`、`.gitattributes` 与本地生成物忽略规则，固定 UTF-8/换行约定并减少 GitHub 提交噪声。
- 清理项目定位文案和“快照份”历史笔误，保持 `名称_yy-mm-dd` 命名规则不变。
- Ruff 静态与格式检查通过；HTML、桌面 UI、源码编码定向测试 14 项通过。
- 真实生成 HTML 的交互脚本通过 Node 语法检查，指定 SVG 路径存在，旧 Emoji/占位符不存在。
- 完整 66 项测试通过，PowerShell 7 重建成功；新 EXE 实测同时生成 HTML 和 SQLite。
- 新 EXE SHA-256：`80DA919452F3125AF89319DC9D91B8926D26E89D912B46B40839BD9CCF0E2889`。

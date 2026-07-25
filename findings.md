# 目录树视觉重构发现

## 参考图差异

- 目标树的展开框位于层级虚线上，所有层级共享固定的 18px 缩进网格。
- 叶子目录没有空的展开框，但必须保留与展开框等宽的连接线占位。
- 文件夹图标为扁平浅黄色，不使用系统 Emoji、黑色描边或明显渐变。
- 当前目录的浅蓝背景从文件夹图标区域开始连续延伸，文字不加粗。
- 根目录不显示展开框；一级子目录的展开框与根目录下方第一条竖线对齐。
- 当前实现基于浏览器原生 `details/summary`，原生点击区域、marker 和自定义伪元素相互影响，难以稳定控制基线和连线。

## 重构决定

改用显式 `div` 树节点、独立展开按钮和子节点容器；继续复用现有目录数据、选择事件和差异红点逻辑。

## 验收限制

浏览器安全策略禁止自动访问本地 `file://` 页面，不能通过其他浏览器接口绕过。自动验收改为 HTML 结构、CSS 几何规则、JavaScript 语法和交互标记测试；真实 HTML 仍会作为最终产物生成。


## 2026-07-25 中文文本问号化诊断

- `src/diskhtml/cli.py`、`src/diskhtml/exe_cli.py` 和 `src/diskhtml/scanner.py` 中存在真实的用户可见问号文本。
- `src/diskhtml/ui.py` 中模块说明、类说明和方法说明共存在大量真实问号文本。
- Windows PowerShell 当前输出编码与 UTF-8 不一致时，会把有效 UTF-8 中文显示为乱码；这种现象只影响终端显示，不等于文件已损坏。
- 若中文经不支持该字符集的命令管道或默认编码写回，字符会在编码阶段被替换成 ASCII 问号；此时原字符信息已经丢失，无法通过重新解码恢复，只能依据代码语义重建。
- 修复过程使用 UTF-8 无 BOM 写回，并通过逐行原内容校验限制修改范围。
- 新增 AST 字符串检查，阻止连续问号或 Unicode 替换字符进入 Python 字符串常量。

- Git 历史进一步确认：提交 `48286dd` 一次性引入了 60 行连续问号，提交 `4eb247c` 引入了 4 行；这符合批量 PowerShell 文本替换时发生编码降级的特征，而不是人工逐字修改。
- 因此可确认直接原因是非 UTF-8 的 PowerShell 文本传递或写回链路；控制台代码页不一致是诱因，但只有在损坏内容被写回文件时才会形成源码中的真实问号。


## 2026-07-25 PowerShell 7 与 Unicode 转义检查

- 系统已安装 PowerShell 7.6.4，路径由 `pwsh.exe` 命令解析。
- 当前自动化终端宿主仍是 Windows PowerShell 5.1，安装 7.x 不会自动替换系统内置 `powershell.exe`。
- 项目运行时代码仅 `src/diskhtml/disk.py` 硬编码调用 `powershell.exe`；应改为优先 PowerShell 7，同时保留 5.1 回退以兼容未安装 7.x 的电脑。
- 非必要中文转义集中在 `archive_ui.py`、`html_archive.py`、`scanner.py` 及相关测试。
- `html_archive.py` 中用于脚本安全转义的 `\u003c`、`\u003e`、`\u0026` 必须保留；CSV 的 `\ufeff` 是 UTF-8 BOM 功能字符，也应保留。
- 两次尝试通过嵌套 PowerShell 命令查看源码均因外层 5.1 提前处理引号或变量而解析失败；后续不再使用该嵌套方式。

- 实测同一只读磁盘查询：PowerShell 7.6.4 为约 2.42 秒，Windows PowerShell 5.1 为约 1.26 秒；7.x 功能正常但首次加载 Storage 模块更慢。
- 扫描恢复测试原先仅等待 2 秒，无法覆盖 PowerShell 7 的正常启动时间，已调整为 5 秒。
- 确认快照默认文件名、测试和既有命名约定均使用下划线，保持 `名称_yy-mm-dd.html`。


## 2026-07-26 图标、磁盘信息与桌面 UI 分析

- `volumes` 表已记录盘符、卷 GUID、卷标、文件系统、总容量、可用容量、磁盘型号、磁盘序列号、分区信息和采集错误。
- 快照数据构建会把完整 `volume` 记录嵌入 HTML；当前缺口是页面没有将这些数据展示给用户。
- HTML 顶部 `snapshot-icon` 仍是文本符号，应替换为用户指定的内联 SVG，保持离线打开。
- 桌面界面使用普通 `QTabWidget`，当前样式只在选中项底部显示细蓝线，任务边界不明显。
- 采用等宽分段导航并配合 Qt 内置图标，可以在不改变任务数据和调用入口的情况下显著提高辨识度。
- 主窗口当前仅调用 `resize(860, 590)`，仍可自由缩放；应改为 `setFixedSize(900, 650)`。
- 当前快照输出实现和测试均使用 `名称_yy-mm-dd.html`，本次保持下划线规则。

## 2026-07-26 文件列表 SVG 与 GitHub 清理审计

- 旧文件列表用 Emoji 和方框字符标识条目；无搜索时 `appendHighlighted` 会重写父节点文本，导致先插入的图标节点被移除。
- 新实现使用 `createElementNS` 创建内联 SVG，严格采用指定的文件夹与文件路径，不依赖外部图标库或 CDN；名称文本改为追加文本节点，因此搜索和非搜索状态都保留图标。
- `DropPathEdit.setText()` 已自动触发 `textChanged`，原 `path_dropped` 信号及四处连接会重复计算建议输出路径，可以安全移除。
- `html_archive.py` 的三个私有包装函数只转发到 `archive_ui.py`，没有额外校验或调用方，已直接使用渲染函数。
- Git 未跟踪构建目录、虚拟环境、HTML 或 SQLite 产物；历史测试临时目录因沙箱权限残留，加入忽略规则后不再污染 Git/Ruff 扫描。
- 项目说明中“快照份”是历史笔误，“冷备份”也不符合当前定位，统一为目录快照、文件 Hash 与离线 HTML 比对。
- 浏览器安全策略禁止自动打开本地 `file://` 报告；真实生成 HTML 已改用 JavaScript 语法检查、SVG 路径检查和自动化测试验证。

## 2026-07-26 单文件 EXE 初步诊断

- 截图明确显示启动器正在查找同目录下的 `_internal/python312.dll`，这符合 PyInstaller `onedir` 发布包中只复制主 EXE、遗漏 `_internal` 目录时的错误。
- 需要检查构建脚本是否使用默认 `onedir`/`COLLECT` 模式；若用户要求“单 EXE”，应改为 `onefile`，并用脱离构建目录的独立副本验收。

## 2026-07-26 打包脚本确认结果

- `scripts/build_windows.ps1` 只传入 `--windowed`，没有 `--onefile`，因此 PyInstaller 使用默认 `onedir`。
- 当前产物结构为 `build\dist\DiskHTML\DiskHTML.exe` 加 `build\dist\DiskHTML\_internal\python312.dll` 等依赖；只复制 EXE 必然失败。
- 单文件构建应输出到 `build\dist\DiskHTML.exe`，并在构建前清理旧的 `build\dist\DiskHTML` 目录，避免用户继续误取旧启动器。
- `docs/diskhtml-exe-guide.md`、`docs/windows-build.md` 和 `docs/release-checklist.md` 仍引用旧的目录式产物路径，需要同步更新。

## 2026-07-26 文档与目录树实现检查

- Windows 构建文档、EXE 指南和发布清单都写成旧的 `build\dist\DiskHTML\DiskHTML.exe`，并包含已不符合当前三任务页界面的人工验收描述，需要一并维护。
- 发布清单脚本接受任意发布目录，因此 onefile 模式可直接以 `build\dist` 为包目录，无需修改脚本数据格式。
- 左侧目录树当前仍用 `.folder-icon` CSS 矩形和伪元素绘图；展开状态只控制箭头与子容器，没有参与图标渲染。
- 应抽取通用的 Lucide SVG DOM 创建函数：文件列表继续使用关闭文件夹图标，目录树根据 `expandedPaths` 使用关闭或打开路径；根节点始终视为打开。

## 2026-07-26 目录树 SVG 实现方案

- 现有 `entryTypeIcon` 已具备 SVG DOM 创建流程，但路径、类别和 SVG 属性混在一个函数内。
- 将其拆为通用 `lucideIcon`、常量路径、文件列表 `entryTypeIcon` 和目录树 `treeFolderIcon`，可以避免重复 SVG 属性代码。
- 目录树每次展开/折叠都会重新执行 `renderTree`，因此只需把 `expandedPaths` 状态传给 `treeFolderIcon` 即可同步切换图标；根节点始终使用打开图标，无子目录的叶子节点使用关闭图标。

## 2026-07-26 发布方式最终决定

- 用户确认可以不是单文件，但必须是打包后的 EXE。
- 采用显式 PyInstaller `onedir`：启动更直接，也避免 onefile 每次启动解压 Qt 运行库；构建后自动生成包含 `DiskHTML.exe` 与 `_internal` 的 ZIP。
- 用户分发和复制的是 ZIP 或完整解压后的 `DiskHTML` 目录，不能只复制其中的 EXE。

## 2026-07-26 完整发布包运行结果

- PowerShell 7 干净构建成功，生成目录式 EXE 和 `build\release\DiskHTML-win-x64.zip`。
- ZIP 解压到独立的 `C:\tmp` 后，`DiskHTML\DiskHTML.exe` 与 `DiskHTML\_internal\python312.dll` 均存在。
- 从解压目录运行 `snapshot` 退出码为 0，成功生成 HTML 和 SQLite；报告同时包含关闭/打开文件夹 SVG。
- EXE SHA-256：`28BCB563496FFE24E25EDBA6FE4961880C3273CF1D725729AEDA688290DC212F`。
- ZIP SHA-256：`72EC4E325A8A5A4984CA6AEEAE52280447DF6F2277BCADCFCC28DF5869AF5FEE`。

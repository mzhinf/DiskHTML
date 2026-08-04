# Windows 构建与验收

## 构建边界

DiskHTML 的实际构建器是 Python 和 PyInstaller，不要求 PowerShell。主入口 `scripts/build_windows.py` 负责：

1. 只在项目 `build/` 范围内清理旧产物；
2. 调用项目 `.venv` 中的 PyInstaller；
3. 显式生成 `onedir` 目录包；
4. 检查 `DiskHTML.exe` 与 `_internal`；
5. 生成可直接分发的 ZIP。

`scripts/build_windows.ps1` 只是可选薄包装，便于已有 PowerShell 操作习惯；它不包含清理、PyInstaller 参数或压缩逻辑。

## 环境与命令

要求 Windows 10/11、Python 3.12 和项目虚拟环境。构建器会从运行环境识别架构，当前发布契约仅接受 x64；其他架构会在打包前明确停止，不能生成错误标记为 x64 的 ZIP：

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
.\.venv\Scripts\python.exe .\scripts\build_windows.py --clean
~~~

### GitHub Actions 范围

GitHub Actions 只执行格式、静态检查和单元测试，不构建、不上传 Windows 发布包。这样 CI 保持为通用的源码质量门禁，不与本机发布运行时、PyInstaller 或许可证资料耦合。

正式 Windows 发布包必须在维护者的受控本地环境中使用本节命令构建，并继续执行 `verify_release.py`。构建器会从最终目录反向生成并验证许可证材料；许可证来源未核验时会停止发布，而不会生成不完整 ZIP。
可选的 PowerShell 包装命令：

~~~powershell
pwsh.exe -NoLogo -NoProfile -File .\scripts\build_windows.ps1 -Clean
~~~

两条命令生成相同产物：

| 产物 | 路径 | 用途 |
|---|---|---|
| 启动程序 | `build\dist\DiskHTML\DiskHTML.exe` | 完整目录包内的入口，不能单独复制 |
| 运行库 | `build\dist\DiskHTML\_internal\` | Python、Tcl/Tk 和程序依赖 |
| 发布包 | `build\release\DiskHTML-win-x64.zip` | 应交付给用户的完整便携包 |

## 自动验收

先运行质量检查，再验证发布 ZIP：

~~~powershell
.\.venv\Scripts\python.exe -m ruff format --check src scripts tests
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe .\scripts\verify_release.py .\build\release\DiskHTML-win-x64.zip
~~~

发布验证脚本会把 ZIP 解压到独立临时目录，检查 `DiskHTML.exe` 和 `_internal\python3*.dll`，校验内嵌 `pyproject.toml` 的版本，运行 `--version`，然后用含中文文件名的样本实际生成 HTML 和 SQLite。它验证的是用户收到的 ZIP，而不是直接调用 Python 源码。

## 人工验收

1. 在空目录完整解压 ZIP，确认只有一个顶层 `DiskHTML` 目录。
2. 双击 EXE，确认三个任务页为“生成目录快照”“生成比对报告”“从 SQLite 生成”。
3. 生成含中文、空目录和普通文件的小型快照，在浏览器离线打开。
4. 从 HTML 中选择一个非根目录，与本机目录生成比对报告。
5. 检查搜索、排序、目录跳转、SHA-256、状态颜色和文件链接。
6. 扫描过程中验证暂停、继续、取消；任务完成后验证“打开 HTML”和“打开所在文件夹”。
7. 在未安装项目 Python 环境的 Windows 10 和 Windows 11 上各验收一次。

## PowerShell 运行时说明

构建不依赖 PowerShell，但当前 EXE 为满足硬盘型号、序列号和分区记录需求，会在扫描时优先调用 `pwsh.exe`，并兼容回退到 `powershell.exe`。这项查询失败时只记录 `capture_error`；容量、卷标、文件系统、Hash、HTML 和 SQLite 仍会正常处理。

# Windows 发布构建

项目提供 PyInstaller 图形界面构建脚本。构建前在项目虚拟环境安装可选依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
```

执行构建：

```powershell
.\scripts\build_windows.ps1
```

产物位于 `build\dist\DiskHTML\DiskHTML.exe`。脚本以 `scripts\gui_entry.py` 作为入口，确保使用包导入启动 PyQt6 界面。可使用 `-Clean` 清理旧构建目录后重新构建。

发布前至少执行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

建议在干净的 Windows 10/11 环境中运行生成的可执行文件，完成项目新建、扫描、恢复、比较、报告打开和关闭重启恢复验收。
# CLI 操作手册

所有命令均使用项目虚拟环境中的解释器：

```powershell
.\.venv\Scripts\python.exe -m diskhtml --help
```

## 扫描与恢复

```powershell
.\.venv\Scripts\python.exe -m diskhtml scan .\archive.sqlite3 D:\资料 --workers 2 --queue-size 32 --chunk-size 4194304 --sha512
.\.venv\Scripts\python.exe -m diskhtml status .\archive.sqlite3
.\.venv\Scripts\python.exe -m diskhtml resume .\archive.sqlite3 <扫描标识>
```

`scan` 完成后输出扫描标识。`status` 输出 JSON；若扫描被取消或失败，可使用 `resume` 从已提交文件边界继续。

## 导出与离线浏览

```powershell
.\.venv\Scripts\python.exe -m diskhtml export .\archive.sqlite3 <扫描标识> .\扫描报告
```

报告目录必须不存在。生成后在资源管理器中打开 `扫描报告\report.html`；报告完全使用本地资源。

## 比较与复验

```powershell
.\.venv\Scripts\python.exe -m diskhtml compare .\archive.sqlite3 D:\旧副本 E:\新副本
.\.venv\Scripts\python.exe -m diskhtml export .\archive.sqlite3 <比较标识> .\比较报告 --compare
.\.venv\Scripts\python.exe -m diskhtml verify .\archive.sqlite3 <历史扫描标识> E:\当前副本
```

`compare` 扫描两个当前路径后比较；左侧是旧来源、右侧是新来源。`verify` 将当前路径与历史扫描比较。比较报告入口为 `比较报告\compare_report.html`。

## 导入与维护

```powershell
.\.venv\Scripts\python.exe -m diskhtml import .\新项目.sqlite3 .\已有项目.sqlite3
.\.venv\Scripts\python.exe -m diskhtml check-db .\新项目.sqlite3
```

`import` 通过 SQLite 备份导入已有项目；源与目标不能相同。所有参数错误与运行错误均以中文输出，并以非零退出码结束。

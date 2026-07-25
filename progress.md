# 进度记录

## 2026-07-25：快照命名与目录树样式

- 快照默认 HTML 文件名已调整为 `源目录-yy-mm-dd.html`；与之对应的 SQLite 索引自动使用同名 `源目录-yy-mm-dd.sqlite3`。
- HTML 快照摘要新增本地时区的生成时间，格式为 `yyyy-mm-dd hh-mm`。
- 目录树已改为细虚线层级、绘制的黄色文件夹图标、轻量方框 `+ / -` 控件与浅蓝选中行。
- 针对本次修改运行 11 项 HTML 与桌面界面回归测试，全部通过。
- 已通过离线 JavaScript 语法校验并重新构建 `build\dist\DiskHTML\DiskHTML.exe`。

## 2026-07-25：目录树组件重构

- 已移除目录树对原生 `details/summary` 的依赖，改为显式树节点、展开按钮、标签按钮和子节点容器。
- 树形几何统一为 18px 层级缩进、13px 展开框、24px 行高和 16px 文件夹图标。

- 11 项 HTML/桌面界面回归测试通过，全项目 Ruff 检查通过，离线 JavaScript 语法检查通过。
- 新版 EXE 已生成真实样本 `reworked.html` 和 `reworked.sqlite3`；样本包含显式树节点和展开按钮，不包含旧的 `createElement('details')`。

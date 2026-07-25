# 进度记录

## 2026-07-25：快照命名与目录树样式

- 快照默认 HTML 文件名已调整为 `源目录-yy-mm-dd.html`；与之对应的 SQLite 索引自动使用同名 `源目录-yy-mm-dd.sqlite3`。
- HTML 快照摘要新增本地时区的生成时间，格式为 `yyyy-mm-dd hh-mm`。
- 目录树已改为细虚线层级、绘制的黄色文件夹图标、轻量方框 `+ / -` 控件与浅蓝选中行。
- 针对本次修改运行 11 项 HTML 与桌面界面回归测试，全部通过。
- 已通过离线 JavaScript 语法校验并重新构建 `build\dist\DiskHTML\DiskHTML.exe`。

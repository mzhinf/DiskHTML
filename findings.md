# 当前任务发现

- 生成快照时，桌面界面只需推荐 HTML 输出名；同名 SQLite 文件由快照服务根据 HTML 后缀自动导出。
- HTML 负载中已包含 `generated_at`，可在离线页面本地时区转换为固定格式。
- 目录树采用 HTML `details/summary`，可仅替换 CSS 与图标渲染，不需修改快照数据或目录跳转逻辑。

# 任务计划：升级 PowerShell 配置并清理中文转义

## 目标

确认 PowerShell 7 可用，将项目内仍依赖 Windows PowerShell 5.1 的调用调整为 PowerShell 7，并把无必要的中文 Unicode 转义改为直接 UTF-8 中文。

## 阶段

- [x] 确认当前宿主与 PowerShell 7 安装状态
- [x] 检查项目脚本和文档中的 PowerShell 调用
- [x] 分类扫描代码中的 Unicode 中文转义
- [x] 更新配置、脚本、源码和回归测试
- [x] 运行测试并重建 DiskHTML.exe
- [x] 提交修改并总结

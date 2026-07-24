# 性能基准

使用扫描基准脚本，在指定的源盘和输出盘上运行一次完整扫描和离线报告导出。输出目录必须不存在；完成后其中会包含项目数据库、报告目录和 \`result.json\`。

## 运行方法

HDD 和 SSD 应分别选择相同的数据集、不同的输出目录执行。HDD 的保守起点是单线程和较小队列，避免随机寻道；SSD 可从当前默认的两线程、32 项队列开始。

~~~powershell
.\.venv\Scripts\python.exe scripts\benchmark_scan.py D:\样本 D:\DiskHTML-benchmark-hdd --workers 1 --queue-size 8
.\.venv\Scripts\python.exe scripts\benchmark_scan.py E:\样本 E:\DiskHTML-benchmark-ssd --workers 2 --queue-size 32
~~~

可通过 \`--chunk-size\`、\`--workers\`、\`--queue-size\` 和 \`--sha512\` 调整测试条件。报告时应记录所用的介质、数据集、参数和 JSON 原始结果，不能混合不同条件的结果。

## 指标

- \`scan.throughput_bytes_per_second\`：包含扫描编排在内的端到端 Hash 吞吐。
- \`memory.peak_working_set_bytes\`：扫描和报告导出期间当前进程的 Windows 峰值工作集。
- \`storage.database_bytes\` 与 \`storage.report_bytes\`：数据库和离线报告的实际磁盘占用。
- \`scan.seconds\` 与 \`report.seconds\`：扫描及报告生成耗时。

## 建议测试集

- 小样本：覆盖快速冒烟、中文与特殊字符路径。
- 海量元数据：以大量小文件检验内存是否保持有界。
- 超大文件：检验读取块大小、吞吐和报告体积。
- 权限错误、路径边界及取消后恢复：使用独立测试目录确认错误审计和恢复语义。

当前仓库仅完成小样本冒烟验证；正式 HDD/SSD 测量和 300 万文件压力结果应作为发布证据单独保存。

# 暂停、取消与恢复语义

## 文件边界

恢复点是“已在 SQLite 事务中完整提交的文件”。进程中断时，正在计算的单个文件从头读取，
不序列化 `hashlib` 的内部状态。

## 状态转换

- `PENDING` 可进入 `SCANNING`、`CANCELLED` 或 `FAILED`。
- `SCANNING` 可进入 `PAUSED`、`COMPLETED`、`CANCELLED` 或 `FAILED`。
- `PAUSED` 可继续到 `SCANNING`，也可取消或失败。
- `CANCELLED` 和 `FAILED` 保留已提交结果，可显式恢复到 `SCANNING`。
- `COMPLETED` 是终态，不能恢复或重新打开写入。

暂停只阻止提交新的文件任务，并等待文件边界；取消应尽快停止派发，已完成的事务不回滚。

## 恢复复用条件

已有记录只有同时满足以下条件才可复用：

1. `hash_status` 为 `OK`；
2. 文件大小与记录一致；
3. 纳秒修改时间与记录一致。

不满足条件的文件必须从头重新计算。权限错误、文件消失和扫描中变化都要写入错误记录，
不能静默跳过。

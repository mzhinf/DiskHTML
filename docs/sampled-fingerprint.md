# 固定预算采样指纹

`diskhtml.sampled_hash.sampled_sha256` 为大文件提供固定次数、固定字节预算的快速预检。它只使用 Python 标准库 SHA-256，不依赖额外哈希库。

> 采样指纹只覆盖文件的少量区域，只适合快速预检。它不是完整内容一致性证明，也不能替代完整 SHA-256。

## 接口

~~~python
from diskhtml.sampled_hash import sampled_sha256

result = sampled_sha256(
    path,
    sample_budget=8 * 1024 * 1024,
    sample_count=8,
)
~~~

参数规则：

- `sample_budget` 是计划读取的字节预算，必须大于 0；
- `sample_count` 是请求的数据块数量，范围为 2 到 32；
- 数据块大小由 `ceil(sample_budget / sample_count)` 自动计算，不作为主要配置；
- 预算内文件完整读取，返回标准完整 SHA-256；
- 超过预算的文件从头到尾均匀规划偏移，包含文件头和文件尾，并按去重后的升序读取，避免 HDD 上不必要的磁头往返。

当文件很小而预算更小时，可用的唯一偏移可能少于请求次数。此时不会重复寻道，`actual_sample_count` 会报告去重后的实际读取次数。

## 结果

结果是字典，包含：

| 字段 | 含义 |
|---|---|
| `mode` | `full` 或 `sampled` |
| `algorithm` | `full-sha256` 或 `sampled-sha256-<预算MB>_<请求次数>` |
| `digest` | 小写十六进制 SHA-256 |
| `file_size` | 计算前读取的文件大小 |
| `sample_budget` | 请求的字节预算 |
| `sample_count` | 请求的采样次数 |
| `actual_sample_count` | 实际读取的去重数据块数量 |
| `block_size` | 完整文件大小或自动计算的采样块大小 |
| `sampled_bytes` | 实际参与计算的内容字节数 |

默认配置的采样算法标识是 `sampled-sha256-8_8`。标识中的 MB 按接口默认值约定使用 `1024²` 字节，并支持非整数预算的无损十进制表示。

## 指纹格式

采样模式使用格式版本 `diskhtml-sampled-sha256-v1`。所有字段都有八字节长度前缀，哈希输入依次包含：

1. 格式版本；
2. 算法标识；
3. 文件大小；
4. 请求预算、请求次数、实际次数和数据块大小；
5. 每个数据块的偏移量、实际读取长度和内容。

文件读取前后会重新检查文件大小和纳秒修改时间。任一值变化，或采样读取长度异常时，函数会抛出 `FileChangedDuringHashError`，调用方不得保存本次结果。
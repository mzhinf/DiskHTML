# 经核验的上游许可证源

本目录保存发布许可证生成器使用的固定版本上游材料，不直接等同于最终发布包组件清单。

## 目录内容

- `upstream/`：完整许可证或厂商授权条款原文；文件名包含对应组件和版本。
- `upstream/provenance.json`：每份材料的组件、版本、来源网址、版本标识、SHA-256 和核验状态。

## 使用规则

许可证来源按以下优先级选择：最终发行物自带文本、相同版本官方源码包、相同 tag/commit 官方仓库、厂商官方授权条款。`scripts/release_licenses.py` 只有在最终发布目录出现对应组件且版本证据匹配时，才会复制这些材料。

当前缓存覆盖 Lucide、python-build-standalone 运行时组件、OpenSSL、SQLite 和 Microsoft Visual C++ Runtime。Tcl/Tk 许可证优先直接取自最终发布目录 `_tk_data/license.terms`，Python 和 PyInstaller 优先取自当前构建环境中实际打包版本的发行元数据。

增删或升级运行时后，必须同步更新许可证原文、`upstream/provenance.json`、组件识别规则和测试；无法确认的信息必须让构建失败并进入人工复核，不得猜测。

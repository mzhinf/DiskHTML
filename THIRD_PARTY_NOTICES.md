# 第三方组件说明

DiskHTML 自身采用根目录 [LICENSE](LICENSE) 中的 MIT License。本文件说明仓库采用的第三方材料与发布机制；最终 ZIP 中具有约束力的逐组件清单由构建流程根据实际产物生成，位于 `THIRD-PARTY-NOTICES.txt` 和 `licenses/`。

## 桌面运行时

桌面界面使用 Python 标准库 `tkinter/ttk`。Windows 发布包实际携带 Tcl/Tk 运行时，不再包含 PySide6、Shiboken6 或 Qt 动态库。Tcl/Tk 的完整许可证从最终产物 `_tk_data/license.terms` 复制并纳入发布包。

## 内嵌图标

桌面界面与离线 HTML 使用 Lucide 图标。仓库固定使用 Lucide 1.27.0 的许可证文本；其中 Lucide 内容采用 ISC License，部分源自 Feather 的内容采用 MIT License。

## 发布包反向审计

`scripts/release_licenses.py` 只根据 `build/dist/DiskHTML/` 中实际存在的 Python 运行时、Tcl/Tk、PyInstaller、Lucide 素材和原生库生成声明。当前受规则覆盖的组件包括 Python、PyInstaller、Tcl/Tk、Lucide、bzip2、Expat、libffi、XZ/liblzma、mpdecimal、zlib、OpenSSL、SQLite 和 Microsoft Visual C++ Runtime。

构建发现未知组件、版本无法确认、许可证源缺失、声明文件不存在或 Qt 残留时会停止，不会猜测许可证信息。经核验的上游来源、版本和 SHA-256 记录在 [`third_party/license_sources/upstream/provenance.json`](third_party/license_sources/upstream/provenance.json)。详细流程见 [`docs/release-licenses.md`](docs/release-licenses.md)。

# Windows 发布许可证包

## 输出结构

Windows 发行物是 PyInstaller `onedir` 目录包。`scripts/build_windows.py` 在创建 ZIP 前调用 `scripts/release_licenses.py`，并在发布目录根部生成：

```text
DiskHTML/
├─ LICENSE.txt
├─ THIRD-PARTY-NOTICES.txt
├─ licenses/
├─ DiskHTML.exe
└─ _internal/
```

- `LICENSE.txt`：逐字节复制维护者确认的根目录 `LICENSE`，构建器不会推测或改写项目许可证。
- `THIRD-PARTY-NOTICES.txt`：英文纯文本声明，按组件类别列出名称、版本、许可证类型、版权、许可证文件和网站。
- `licenses/`：最终发布包实际包含组件的完整许可证文本，每个声明都必须指向真实文件。

## 识别原则

许可证生成器从最终 `build/dist/DiskHTML/` 反向识别组件，不会把开发环境中已安装但未打包的包加入清单。当前规则检查：

1. Python 运行时与标准库；
2. PyInstaller 启动器和运行钩子；
3. Tkinter 对应的 Tcl/Tk 运行时；
4. 实际内嵌的 Lucide 图标；
5. bzip2、Expat、libffi、XZ/liblzma、mpdecimal、zlib、OpenSSL、SQLite 和 Microsoft Visual C++ Runtime 等原生组件。

Python、Tcl/Tk 和原生库版本分别由运行时文件、Tcl 初始化脚本、PE 文件版本或固定构建来源交叉确认。随 Python 运行时静态进入 `python3*.dll` 的组件也必须由运行时 `BUILD` 与来源登记表中的同修订证据覆盖。

## 许可证来源优先级

1. 最终运行时或发行包自带的许可证文本；
2. 完全相同版本的官方源码发行包；
3. 完全相同 tag 或 commit 的官方仓库；
4. 厂商官方授权条款和 REDIST 文档。

经核验的上游文本保存在 `third_party/license_sources/upstream/`，来源网址、版本、SHA-256 和核验状态记录在 `third_party/license_sources/upstream/provenance.json`。缓存文本只有在组件规则同时确认最终产物证据和版本时才会进入发布包。

## 自动阻断与验证

构建会在下列情况停止：

- 项目许可证缺失或存在多个候选文件；
- 实际组件没有规则或许可证来源；
- 版本、版权或许可证类型无法确认；
- `License File` 指向不存在的文件；
- 声明组件与最终产物不一致；
- Tkinter 发布包中残留 PySide6、Shiboken6 或 Qt 文件。

`build/release/license-audit.json` 保存组件证据、许可证来源和待复核原因。`scripts/verify_release.py` 会解压最终 ZIP，再次检查目录结构、Tkinter/Tcl-Tk 运行时、许可证引用、组件集合以及 EXE 的实际快照生成能力。

# 贡献指南

## 开发环境

使用 Python 3.12 和项目根目录 `.venv`：

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
~~~

不要把 `.venv`、`build`、HTML、SQLite、日志、IDE 配置或本机路径提交到仓库。

## 代码说明规则

- 每个自有 `.py` 文件必须以模块 docstring 说明用途。
- 每个 `.ps1` 和 GitHub Actions 工作流必须以文件头注释说明用途。
- 类和承担业务语义的函数使用具体说明，禁止 `Helper`、`TODO later` 等占位文字。
- `__init__`、明显的属性访问器和标准协议方法可不重复说明；复杂分支应解释“为什么”，不要逐行翻译代码。
- 生成文件、第三方文件和空包标记可豁免，但必须在文档或第三方声明中说明来源。

`tests/test_source_encoding.py` 会自动检查 Python/PowerShell 文件级说明和 UTF-8 编码。

## 产品边界

提交前确认没有混淆两个界面：

- EXE 只选择输入、扫描和生成；
- HTML 只离线浏览快照或比对报告。

默认桌面任务只有生成目录快照、生成比对报告、从 SQLite 生成。新增入口或改变比较语义时，先更新 `docs/html-archive-design.md` 和 `docs/architecture.md`。

## 质量检查

~~~powershell
.\.venv\Scripts\python.exe -m ruff format src scripts tests
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
git diff --check
~~~

涉及 HTML UI 时，不能只增加 CSS/JavaScript 字符串断言；需要验证实际生成数据和用户行为，并在 PR 中附离线页面截图及手工检查项。涉及发布时，还要运行：

~~~powershell
.\.venv\Scripts\python.exe .\scripts\build_windows.py --clean
.\.venv\Scripts\python.exe .\scripts\verify_release.py .\build\release\DiskHTML-win-x64.zip
~~~

## 编码与提交

- 源码、测试、文档使用 UTF-8；PowerShell 脚本按仓库规则使用 CRLF。
- 不使用依赖默认代码页的 shell 管道批量写回源码；修改后必须运行编码测试。
- 一个提交只处理一个关注点，避免把数据逻辑、HTML UI、桌面 UI、打包和文档重写混在一起。
- 面向用户的变更同步更新 `CHANGELOG.md` 和 `docs/README.md`。
"""DiskHTML 桌面界面的中英文文案与语言状态。"""

from __future__ import annotations

from collections.abc import Mapping

_DEFAULT_LANGUAGE = "zh-CN"
_LANGUAGE = _DEFAULT_LANGUAGE

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh-CN": {
        "WINDOW_TITLE": "DiskHTML - HTML 快照生成器",
        "READY": "就绪",
        "LANGUAGE": "语言",
        "LANGUAGE_CHINESE": "中文",
        "LANGUAGE_ENGLISH": "English",
        "TAB_SNAPSHOT": "生成目录快照",
        "TAB_COMPARE": "生成比对报告",
        "TAB_SQLITE": "从 SQLite 生成",
        "SNAPSHOT_HEADING": "生成目录快照",
        "SNAPSHOT_DESCRIPTION": "生成可离线打开的 HTML 文件快照。",
        "COMPARE_HEADING": "生成比对报告",
        "COMPARE_DESCRIPTION": "生成一个可离线打开的 HTML，比对已有快照与当前目录。",
        "SQLITE_HEADING": "从 SQLite 生成",
        "SQLITE_DESCRIPTION": "不重新扫描原目录，直接生成新版本 HTML。",
        "SOURCE_DIRECTORY": "源目录",
        "BASELINE_SNAPSHOT": "基准快照",
        "CHECK_DIRECTORY": "待检查目录",
        "OUTPUT_HTML": "输出 HTML",
        "OUTPUT_REPORT": "输出报告",
        "SQLITE_INDEX": "SQLite 快照索引",
        "SELECT_DIRECTORY": "选择目录",
        "SELECT_SNAPSHOT": "选择快照",
        "SELECT_SQLITE": "选择 SQLite",
        "CHANGE_LOCATION": "更改位置",
        "FOLLOW_LINKS": "跟随软链接和 Windows 重解析点",
        "CREATE_SNAPSHOT": "生成快照 HTML",
        "CREATE_COMPARE": "生成比对 HTML",
        "CREATE_SQLITE": "从 SQLite 生成 HTML",
        "SNAPSHOT_ROOT": "快照根目录",
        "SNAPSHOT_DIRECTORY": "快照内目录",
        "SELECT_ARCHIVED_DIRECTORY": "选择快照内目录",
        "SNAPSHOT_SOURCE_HELP": "需要保存为快照的文件夹。",
        "SNAPSHOT_OUTPUT_HELP": "将同时生成同名 SQLite 索引。",
        "ARCHIVE_HELP": "之前生成的 DiskHTML HTML 快照。",
        "CHECK_DIRECTORY_HELP": "当前需要与快照比较的实际文件夹。",
        "COMPARE_OUTPUT_HELP": "比对结果将保存为可离线打开的 HTML。",
        "SQLITE_HELP": "生成快照时同名保留的 .sqlite3 文件。",
        "SQLITE_OUTPUT_HELP": "新的 HTML 输出文件必须不存在。",
        "PAUSE": "暂停",
        "RESUME": "继续",
        "CANCEL": "取消",
        "OPEN_HTML": "打开 HTML",
        "OPEN_FOLDER": "打开所在文件夹",
        "SUCCESS": "生成成功",
        "TASK_FAILED": "任务失败",
        "CURRENT_STAGE": "当前阶段",
        "CURRENT_PATH": "正在处理的路径",
        "FILES_SCANNED": "已扫描文件数",
        "HASH_PROGRESS": "Hash 进度",
        "WAITING_SCAN": "等待扫描",
        "WAITING_FILE": "等待下一个文件",
        "CREATE_SNAPSHOT_STAGE": "正在生成 HTML 快照。",
        "CREATE_COMPARE_STAGE": "正在扫描待检查目录并生成比对 HTML。",
        "CREATE_SQLITE_STAGE": "正在从 SQLite 生成 HTML。",
        "SCANNING_HASH_STAGE": "正在扫描并计算 Hash",
        "REQUESTED_ACTION": "已请求：",
        "HTML_CREATED": "HTML 已生成",
        "COMPARE_CREATED": "比对 HTML 已生成",
        "DIRECTORY_REQUIRED": "请选择存在的目录。",
        "ARCHIVE_REQUIRED": "请选择存在的 DiskHTML HTML 快照。",
        "SQLITE_REQUIRED": "请选择存在的 SQLite 快照索引。",
        "OUTPUT_HTML_REQUIRED": "输出文件必须是新的 .html 文件。",
        "OUTPUT_EXISTS": "输出 HTML 已存在，请更换一个名称。",
        "OUTPUT_NOT_WRITABLE": "输出目录不存在或不可写。",
        "ARCHIVE_INVALID": "快照格式无效",
        "SELECT_SOURCE_DIRECTORY_TITLE": "选择源目录",
        "SELECT_CHECK_DIRECTORY_TITLE": "选择待检查目录",
        "SELECT_BASELINE_SNAPSHOT_TITLE": "选择基准快照",
        "SELECT_SQLITE_SNAPSHOT_TITLE": "选择 SQLite 快照索引",
        "SAVE_HTML_SNAPSHOT_TITLE": "保存 HTML 快照",
        "SAVE_HTML_COMPARE_TITLE": "保存 HTML 比对报告",
        "SAVE_HTML_FROM_SQLITE_TITLE": "从 SQLite 保存 HTML",
        "HTML_FILE_FILTER": "HTML 文件 (*.html)",
        "SQLITE_FILE_FILTER": "SQLite 文件 (*.sqlite3 *.sqlite)",
        "CONFIRM": "确定",
    },
    "en": {
        "WINDOW_TITLE": "DiskHTML - HTML Snapshot Generator",
        "READY": "Ready",
        "LANGUAGE": "Language",
        "LANGUAGE_CHINESE": "中文",
        "LANGUAGE_ENGLISH": "English",
        "TAB_SNAPSHOT": "Create Snapshot",
        "TAB_COMPARE": "Create Comparison",
        "TAB_SQLITE": "Render from SQLite",
        "SNAPSHOT_HEADING": "Create Directory Snapshot",
        "SNAPSHOT_DESCRIPTION": "Create an HTML snapshot that can be opened offline.",
        "COMPARE_HEADING": "Create Comparison Report",
        "COMPARE_DESCRIPTION": "Create offline HTML that compares an existing snapshot with a current directory.",
        "SQLITE_HEADING": "Render from SQLite",
        "SQLITE_DESCRIPTION": "Create the latest HTML without rescanning the original directory.",
        "SOURCE_DIRECTORY": "Source directory",
        "BASELINE_SNAPSHOT": "Baseline snapshot",
        "CHECK_DIRECTORY": "Directory to check",
        "OUTPUT_HTML": "Output HTML",
        "OUTPUT_REPORT": "Output report",
        "SQLITE_INDEX": "SQLite snapshot index",
        "SELECT_DIRECTORY": "Choose directory",
        "SELECT_SNAPSHOT": "Choose snapshot",
        "SELECT_SQLITE": "Choose SQLite",
        "CHANGE_LOCATION": "Change location",
        "FOLLOW_LINKS": "Follow symbolic links and Windows reparse points",
        "CREATE_SNAPSHOT": "Create Snapshot HTML",
        "CREATE_COMPARE": "Create Comparison HTML",
        "CREATE_SQLITE": "Create HTML from SQLite",
        "SNAPSHOT_ROOT": "Snapshot root",
        "SNAPSHOT_DIRECTORY": "Directory in snapshot",
        "SELECT_ARCHIVED_DIRECTORY": "Choose directory in snapshot",
        "SNAPSHOT_SOURCE_HELP": "The folder to save as a snapshot.",
        "SNAPSHOT_OUTPUT_HELP": "A same-named SQLite index will also be created.",
        "ARCHIVE_HELP": "A DiskHTML HTML snapshot created previously.",
        "CHECK_DIRECTORY_HELP": "The current folder to compare with the snapshot.",
        "COMPARE_OUTPUT_HELP": "The comparison result will be saved as offline HTML.",
        "SQLITE_HELP": "The .sqlite3 file retained alongside a generated snapshot.",
        "SQLITE_OUTPUT_HELP": "The new HTML output file must not already exist.",
        "PAUSE": "Pause",
        "RESUME": "Resume",
        "CANCEL": "Cancel",
        "OPEN_HTML": "Open HTML",
        "OPEN_FOLDER": "Open folder",
        "SUCCESS": "Created successfully",
        "TASK_FAILED": "Task failed",
        "CURRENT_STAGE": "Current stage",
        "CURRENT_PATH": "Processing path",
        "FILES_SCANNED": "Files scanned",
        "HASH_PROGRESS": "Hash progress",
        "WAITING_SCAN": "Waiting to scan",
        "WAITING_FILE": "Waiting for the next file",
        "CREATE_SNAPSHOT_STAGE": "Creating HTML snapshot.",
        "CREATE_COMPARE_STAGE": "Scanning the directory and creating comparison HTML.",
        "CREATE_SQLITE_STAGE": "Creating HTML from SQLite.",
        "SCANNING_HASH_STAGE": "Scanning and calculating hashes",
        "REQUESTED_ACTION": "Requested: ",
        "HTML_CREATED": "HTML created",
        "COMPARE_CREATED": "Comparison HTML created",
        "DIRECTORY_REQUIRED": "Choose an existing directory.",
        "ARCHIVE_REQUIRED": "Choose an existing DiskHTML HTML snapshot.",
        "SQLITE_REQUIRED": "Choose an existing SQLite snapshot index.",
        "OUTPUT_HTML_REQUIRED": "The output file must be a new .html file.",
        "OUTPUT_EXISTS": "The output HTML already exists. Choose a different name.",
        "OUTPUT_NOT_WRITABLE": "The output directory does not exist or is not writable.",
        "ARCHIVE_INVALID": "Invalid snapshot format",
        "SELECT_SOURCE_DIRECTORY_TITLE": "Choose source directory",
        "SELECT_CHECK_DIRECTORY_TITLE": "Choose directory to check",
        "SELECT_BASELINE_SNAPSHOT_TITLE": "Choose baseline snapshot",
        "SELECT_SQLITE_SNAPSHOT_TITLE": "Choose SQLite snapshot index",
        "SAVE_HTML_SNAPSHOT_TITLE": "Save HTML snapshot",
        "SAVE_HTML_COMPARE_TITLE": "Save HTML comparison",
        "SAVE_HTML_FROM_SQLITE_TITLE": "Save HTML from SQLite",
        "HTML_FILE_FILTER": "HTML files (*.html)",
        "SQLITE_FILE_FILTER": "SQLite files (*.sqlite3 *.sqlite)",
        "CONFIRM": "OK",
    },
}


def supported_languages() -> tuple[tuple[str, str], ...]:
    """返回语言代码与当前界面中显示的语言名称。"""

    return (
        ("zh-CN", _TRANSLATIONS[_LANGUAGE]["LANGUAGE_CHINESE"]),
        ("en", _TRANSLATIONS[_LANGUAGE]["LANGUAGE_ENGLISH"]),
    )


def current_language() -> str:
    """返回当前桌面界面语言代码。"""

    return _LANGUAGE


def set_language(language: str) -> None:
    """设置当前桌面界面语言。"""

    if language not in _TRANSLATIONS:
        raise ValueError(f"不支持的界面语言：{language}")
    global _LANGUAGE
    _LANGUAGE = language


def translations(language: str | None = None) -> Mapping[str, str]:
    """返回指定语言或当前语言的只读文案映射。"""

    return _TRANSLATIONS[language or _LANGUAGE]


def __getattr__(name: str) -> str:
    """兼容既有常量访问方式，按当前语言动态返回文案。"""

    try:
        return _TRANSLATIONS[_LANGUAGE][name]
    except KeyError as exc:
        raise AttributeError(name) from exc

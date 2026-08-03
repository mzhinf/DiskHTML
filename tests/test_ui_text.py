"""桌面界面中英文文案模块测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

from diskhtml import ui_text


class UiTextTests(unittest.TestCase):
    """验证两种界面语言的文案键一致且可切换。"""

    def tearDown(self) -> None:
        """每项测试后恢复默认中文，避免影响其他界面测试。"""

        ui_text.set_language("zh-CN")

    def test_supported_languages_have_identical_text_keys(self) -> None:
        """中文与英文必须提供相同的界面文案键。"""

        self.assertEqual(
            set(ui_text.translations("zh-CN")),
            set(ui_text.translations("en")),
        )

    def test_dynamic_constant_access_uses_selected_language(self) -> None:
        """既有常量访问方式必须随当前语言动态返回文本。"""

        ui_text.set_language("en")
        self.assertEqual("Create Snapshot", ui_text.TAB_SNAPSHOT)
        self.assertEqual("Language", ui_text.LANGUAGE)
        ui_text.set_language("zh-CN")
        self.assertEqual("生成目录快照", ui_text.TAB_SNAPSHOT)

    def test_ui_source_has_no_hard_coded_file_dialog_titles(self) -> None:
        """文件选择对话框标题必须使用集中翻译文案。"""

        source = (Path(__file__).parents[1] / "src" / "diskhtml" / "ui.py").read_text("utf-8")
        self.assertNotIn('"Select directory to check"', source)
        self.assertNotIn('"HTML files (*.html)"', source)

    def test_unsupported_language_is_rejected(self) -> None:
        """未知语言代码必须显式报错，避免界面处于半翻译状态。"""

        with self.assertRaises(ValueError):
            ui_text.set_language("fr")


if __name__ == "__main__":
    unittest.main()

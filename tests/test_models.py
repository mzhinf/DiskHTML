"""领域模型和扫描状态机测试。"""

from unittest import TestCase

from diskhtml.models import ScanStatus, validate_scan_transition


class ScanStateTests(TestCase):
    """验证可恢复状态转换契约。"""

    def test_pause_and_resume_are_allowed(self) -> None:
        """运行中的任务可以暂停并继续。"""

        validate_scan_transition(ScanStatus.SCANNING, ScanStatus.PAUSED)
        validate_scan_transition(ScanStatus.PAUSED, ScanStatus.SCANNING)

    def test_cancelled_scan_can_be_resumed(self) -> None:
        """取消保留断点，因此允许显式恢复。"""

        validate_scan_transition(ScanStatus.CANCELLED, ScanStatus.SCANNING)

    def test_completed_scan_is_terminal(self) -> None:
        """完成快照必须保持冻结。"""

        with self.assertRaisesRegex(ValueError, "不允许"):
            validate_scan_transition(ScanStatus.COMPLETED, ScanStatus.SCANNING)

"""比较条目领域内部接口的顺序与字段等价测试。"""

from unittest import TestCase

from diskhtml._comparison_entries import iter_comparison_entries
from diskhtml.models import CompareStatus
from diskhtml.sampled_hash import FULL_SHA256_ALGORITHM, sampled_sha256_algorithm


class ComparisonEntryTests(TestCase):
    """固定六种状态的归并顺序、字段方向和错误文案。"""

    def test_entries_keep_all_statuses_in_path_order(self) -> None:
        """已排序行流应按路径生成六种状态且不改变字段含义。"""

        sampled_algorithm = sampled_sha256_algorithm()
        left = iter(
            (
                self._row("a-error.txt", digest=None, status="ERROR"),
                self._row("b-changed.txt", digest="旧"),
                self._row("c-match.txt", digest="同"),
                self._row("d-missing.txt", digest="缺"),
                self._row("f-precheck.txt", digest="采", algorithm=sampled_algorithm),
            )
        )
        right = iter(
            (
                self._row("a-error.txt", digest="新"),
                self._row("b-changed.txt", digest="新"),
                self._row("c-match.txt", digest="同"),
                self._row("e-added.txt", digest="增"),
                self._row("f-precheck.txt", digest="采", algorithm=sampled_algorithm),
            )
        )

        entries = list(iter_comparison_entries(left, right))

        self.assertEqual(
            [(entry["relative_path"], entry["status"]) for entry in entries],
            [
                ("a-error.txt", CompareStatus.ERROR),
                ("b-changed.txt", CompareStatus.CHANGED),
                ("c-match.txt", CompareStatus.MATCH),
                ("d-missing.txt", CompareStatus.MISSING),
                ("e-added.txt", CompareStatus.ADDED),
                ("f-precheck.txt", CompareStatus.PRECHECK_MATCH),
            ],
        )
        self.assertEqual(entries[0]["error_message"], "左侧文件摘要状态为 ERROR")
        self.assertEqual(
            entries[3],
            {
                "relative_path": "d-missing.txt",
                "status": CompareStatus.MISSING,
                "error_message": None,
                "old_size_bytes": 1,
                "old_sha256": "缺",
                "old_hash_algorithm": FULL_SHA256_ALGORITHM,
                "old_created_time": "创建时间",
                "old_modified_time": "修改时间",
            },
        )
        self.assertEqual(
            entries[4],
            {
                "relative_path": "e-added.txt",
                "status": CompareStatus.ADDED,
                "error_message": None,
                "new_size_bytes": 1,
                "new_sha256": "增",
                "new_hash_algorithm": FULL_SHA256_ALGORITHM,
                "new_created_time": "创建时间",
                "new_modified_time": "修改时间",
            },
        )

    @staticmethod
    def _row(
        relative_path: str,
        *,
        digest: str | None,
        status: str = "OK",
        algorithm: str = FULL_SHA256_ALGORITHM,
    ) -> dict[str, object]:
        """构造字段完整且按路径键可排序的比较输入行。"""

        return {
            "relative_path": relative_path,
            "path_key": relative_path.casefold(),
            "size_bytes": 1,
            "sha256": digest,
            "hash_algorithm": algorithm,
            "hash_status": status,
            "created_time": "创建时间",
            "modified_time": "修改时间",
        }

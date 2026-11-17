"""検索索引（SQLite FTS5）の確認。tests/fixtures/ の小さな規約で試す。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kiyakunote.core import Registry, load_dir  # noqa: E402
from kiyakunote.search import build_index, refs_of, search  # noqa: E402


class SearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = Path(tempfile.mkdtemp()) / "s.db"
        build_index(Registry(load_dir(ROOT / "tests" / "fixtures")), cls.db)

    def test_three_chars_and_more(self):
        rows = search(self.db, "駐車場使用料")
        labels = {r[2] for r in rows}
        self.assertIn("第4条の2", labels)          # 見出し・本文とも枝番の番号で出る

    def test_short_term_like(self):
        rows = search(self.db, "解除")
        self.assertTrue(any(r[2] == "第5条" for r in rows))

    def test_width_normalized(self):
        # 全角・半角の違いを無視して引ける
        self.assertEqual(search(self.db, "３か月"), search(self.db, "3か月"))
        self.assertTrue(search(self.db, "3か月"))

    def test_numbers_are_computed(self):
        # 本文中の参照は展開後の番号で索引される
        rows = search(self.db, "第4条の2の定め")
        self.assertTrue(rows)

    def test_filter_doc(self):
        rows = search(self.db, "使用料", doc="bylaw-parking")
        self.assertTrue(rows and all(r[1] == "bylaw-parking" for r in rows))

    def test_appendix_cells(self):
        rows = search(self.db, "機械式上段", kind="別表")
        self.assertTrue(rows)

    def test_reverse_refs(self):
        out, inc = refs_of(self.db, "art-parking-fee")
        self.assertTrue(any("bylaw-parking" == d for d, _, _ in inc))   # 細則から参照されている


if __name__ == "__main__":
    unittest.main()

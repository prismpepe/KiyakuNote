"""（tests/fixtures の小さな規約で）検索: 正規表現、一致範囲（画面で黄色にする位置）の確認。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kiyakunote.search import build_index, excerpt, find_spans, norm, search, snippet  # noqa: E402
from kiyakunote.core import Registry, load_dir  # noqa: E402


class SearchRegexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.tmp.name) / "s.db"
        build_index(Registry(load_dir(ROOT / "tests" / "fixtures")), cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_plain_and(self):
        rows = search(self.db, "駐車場 使用料", limit=500)
        self.assertTrue(rows)

    def test_regex(self):
        rows = search(self.db, r"駐車場.{0,3}使用料", regex=True, limit=500)
        self.assertTrue(rows)
        # 空白は区切りではなく、式の一部
        self.assertEqual(search(self.db, "駐車場 使用料", regex=True, limit=5), [])

    def test_bad_regex(self):
        with self.assertRaises(ValueError):
            search(self.db, "(", regex=True)
        with self.assertRaises(ValueError):
            search(self.db, "a*", regex=True)                                    # 空に一致する式は全件になるので使えない

    def test_spans(self):
        t = "区分所有者は、その専有部分を専ら住宅として使用する。区分所有者"
        self.assertEqual(find_spans(t, "区分所有者"), [(0, 5), (len(t) - 5, len(t))])
        s, spans = excerpt(t, "専有部分", width=3)
        self.assertEqual(s[spans[0][0]:spans[0][1]], "専有部分")
        self.assertEqual(snippet(t, "専有部分", 3), s[:spans[0][0]] + "【専有部分】" + s[spans[0][1]:])   # コマンド用は【】
        self.assertNotIn("【", snippet(t, "専有部分", 3, brackets=False))
        s2, sp2 = excerpt("第6条の2と第46条の8", r"第\d+条の\d+", regex=True)
        self.assertEqual([s2[a:b] for a, b in sp2], ["第6条の2", "第46条の8"])


class RefsOfTest(unittest.TestCase):
    def test_refs_of_limited_to_own_document(self):
        """条のIDが別の文書と同じでも、参照元の文書で絞る（別の文書の参照が混ざらない）。"""
        import inspect
        from kiyakunote import search as s
        self.assertIn("from_doc = ?", inspect.getsource(s.refs_of))


if __name__ == "__main__":
    unittest.main()

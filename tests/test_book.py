"""冊子（一冊のWord出力）の構成と出力。画面（Tk）は使わない。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kiyakunote import book  # noqa: E402
from kiyakunote.docx_out import build_book  # noqa: E402
from kiyakunote.versions import load_version  # noqa: E402


class BookTest(unittest.TestCase):
    def test_parse(self):
        plan = book.parse_book("# 注釈\n表紙: 題名\n\n目次\n中表紙：区切り\n文書: kiyaku\n別表等: kiyaku\n改訂履歴\n署名\n")
        self.assertEqual(plan, [("表紙", "題名"), ("目次", ""), ("中表紙", "区切り"), ("文書", "kiyaku"), ("別表等", "kiyaku"), ("改訂履歴", ""), ("署名", "")])
        for bad in ("でたらめ: x", "文書:", "目次: x"):
            with self.assertRaises(book.BookError):
                book.parse_book(bad)

    def test_default_and_check(self):
        reg = load_version("WORKTREE")
        plan = book.parse_book(book.default_book_text(reg, "2026年6月1日"))
        errs, notes = book.check_plan(reg, plan)
        self.assertEqual((errs, notes), ([], []))                              # 既定は、全文書が1回ずつ入る
        self.assertIn(("表紙", "2026年6月1日施行"), plan)
        errs, notes = book.check_plan(reg, [("文書", "ない文書")])
        self.assertTrue(errs)
        some = next(d for d in reg.docs.values() if d.kind == "規約")
        errs, notes = book.check_plan(reg, [("文書", some.id)])
        self.assertEqual(errs, [])
        self.assertEqual(bool(notes), len([d for d in reg.docs.values() if d.kind not in ("別表", "別紙", "別図")]) > 1)

    def test_build(self):
        from docx import Document
        reg = load_version("WORKTREE")
        plan = book.parse_book(book.default_book_text(reg))
        revs = [{"resolution": "2020-04-01", "effective": "2020-05-01", "ref": "v1", "notes": [], "changes": ["管理規約 改定"]}]
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "b.docx"
            build_book(reg, plan, out, src_dir=reg.src_dir, revisions=revs)
            doc = Document(str(out))
            text = "\n".join(p.text for p in doc.paragraphs)
            self.assertIn("目　次", text)
            self.assertIn("改訂履歴", text)
            self.assertGreater(len(doc.sections), 3)                          # 表紙・目次・中表紙・文書ごとにページが分かれる
            self.assertIn("TOC", doc.element.xml)


if __name__ == "__main__":
    unittest.main()

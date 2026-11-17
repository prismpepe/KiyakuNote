"""条の編集（変更・新設・削除）の確認。tests/fixtures/ のコピーで行う。"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kisoku import edit  # noqa: E402
from kisoku.core import Registry, load_dir  # noqa: E402
from kisoku.lint import lint  # noqa: E402
from kisoku.render import article_text  # noqa: E402


class EditTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        for f in (ROOT / "tests" / "fixtures").glob("*.md"):
            if not f.name.startswith("expected"):
                shutil.copy(f, self.dir / f.name)
        self.path = self.dir / "kiyaku.md"

    def reg(self):
        return Registry(load_dir(self.dir))

    def test_text_roundtrip(self):
        doc = edit.load_for_edit(self.path)
        art = edit.find_article(doc, "art-def")
        text = edit.article_to_text(art)
        self.assertIn("項 {#art-def-p1}", text)
        self.assertIn("号 {#art-def-p1-i1}", text)
        self.assertEqual(edit.edit_article(doc, "art-def", art.title, text), [])
        edit.save(doc)
        r = self.reg()
        self.assertEqual([f for f in lint(r) if f[0] == "E"], [])

    def test_change_text(self):
        doc = edit.load_for_edit(self.path)
        art = edit.find_article(doc, "art-purpose")
        errs = edit.edit_article(doc, "art-purpose", "目的", "項 {#art-purpose-p1} 改めた本文である。")
        self.assertEqual(errs, [])
        edit.save(doc)
        r = self.reg()
        d = r.docs["kiyaku"]
        self.assertIn("改めた本文である。", article_text(r, d, next(a for a in d.articles if a.id == "art-purpose")))

    def test_add_article_shifts_numbers_and_refs(self):
        doc = edit.load_for_edit(self.path)
        errs, art = edit.add_article(doc, "art-purpose", "新設", "項 新しい条の本文。\n項 第二項。\n号 一つ目の号")
        self.assertEqual(errs, [])
        edit.save(doc)
        r = self.reg()
        d = r.docs["kiyaku"]
        by = {a.id: a.label for a in d.articles}
        self.assertEqual(by[art.id], "第2条")
        self.assertEqual(by["art-def"], "第3条")            # 繰り下がる
        self.assertEqual(by["art-parking-fee"], "第5条の2")  # 枝番も追随
        ids = {a.id for a in d.articles}
        self.assertEqual([f for f in lint(r) if f[0] == "E"], [])
        text = article_text(r, d, next(a for a in d.articles if a.id == art.id))
        self.assertIn("2　第二項。", text)

    def test_add_branch_article(self):
        doc = edit.load_for_edit(self.path)
        errs, art = edit.add_article(doc, "art-purpose", "枝番の条", "項 本文。", branch=True)
        self.assertEqual(errs, [])
        edit.save(doc)
        d = self.reg().docs["kiyaku"]
        self.assertEqual(next(a for a in d.articles if a.id == art.id).label, "第1条の2")

    def test_delete_keeps_slot_and_flags_refs(self):
        doc = edit.load_for_edit(self.path)
        edit.delete_article(doc, "art-parking-fee")
        edit.save(doc)
        r = self.reg()
        d = r.docs["kiyaku"]
        self.assertEqual(next(a for a in d.articles if a.id == "art-parking-fee").deleted, True)
        codes = {f[1] for f in lint(r)}
        self.assertIn("E-DELETED", codes)                   # 削除した条への参照が検出される

    def test_errors(self):
        doc = edit.load_for_edit(self.path)
        self.assertTrue(edit.edit_article(doc, "art-purpose", "目的", "号 いきなり号"))
        self.assertTrue(edit.edit_article(doc, "art-purpose", "目的", ""))
        errs, _ = edit.add_article(doc, "art-purpose", "x", "項 a", new_id="art-def")
        self.assertTrue(errs)

    def test_new_lines_get_ids(self):
        doc = edit.load_for_edit(self.path)
        text = edit.article_to_text(edit.find_article(doc, "art-def")) + "\n項 追加した項。\n号 追加した号。"
        self.assertEqual(edit.edit_article(doc, "art-def", "定義", text), [])
        art = edit.find_article(doc, "art-def")
        self.assertEqual([p.id for p in art.paras][-1], "art-def-p3")
        self.assertEqual(art.paras[-1].items[0].id, "art-def-p3-i1")


if __name__ == "__main__":
    unittest.main()


class PlainTextTest(unittest.TestCase):
    def test_plain_lines_become_paragraphs(self):
        from kisoku.edit import text_to_paras
        paras, errs = text_to_paras("第一の文である。\n第二の文である。", "art-x", set())
        self.assertEqual(errs, [])
        self.assertEqual([p.text for p in paras], ["第一の文である。", "第二の文である。"])

    def test_error_message_explains(self):
        from kisoku.edit import text_to_paras
        _, errs = text_to_paras("書き出しに項がない\n項 本文", "art-x", set())
        self.assertIn("項", errs[0])

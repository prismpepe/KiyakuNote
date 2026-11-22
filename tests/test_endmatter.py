"""巻末の項目（改訂履歴・署名）、Word出力、外部エディタ起動の補助。画面（Tk）は使わない。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kiyakunote import endmatter, mdedit  # noqa: E402
from kiyakunote.docx_out import build_docx  # noqa: E402
from kiyakunote.versions import load_version  # noqa: E402

REVS = [
    {"resolution": "2020-04-01", "effective": "2020-05-01", "ref": "v1", "notes": [], "changes": ["管理規約 改定"]},
    {"resolution": "2022-04-01", "effective": "2022-05-01", "ref": "v2", "notes": ["注記"], "changes": ["・細則 制定", "別表 改定"]},
]


class EndMatterTest(unittest.TestCase):
    def test_history(self):
        self.assertEqual(len(endmatter.history_for(REVS, "WORKTREE")), 2)
        self.assertEqual(len(endmatter.history_for(REVS, "v1")), 1)          # 過去の版は、その施行日まで
        self.assertEqual(len(endmatter.history_for(REVS, "不明なタグ")), 2)
        rows = endmatter.history_rows(REVS)
        self.assertEqual(rows[0], list(endmatter.HEAD))
        self.assertEqual(rows[2][2], "注記\n・細則 制定\n・別表 改定")        # ・は重ねない
        cells = endmatter.history_cells(REVS)
        self.assertTrue(all(th == (r == 0) for r, _, _, _, _, th in cells))

    def test_okugaki(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(endmatter.load_okugaki(d), [])
            (Path(d) / "okugaki.txt").write_text("証する。\n\n2026年4月19日\n\n組合\n理事長　氏名　印\n", encoding="utf-8")
            self.assertEqual(endmatter.load_okugaki(d), ["証する。", "2026年4月19日", "組合\n理事長　氏名　印"])

    def test_docx_endmatter(self):
        from docx import Document
        reg = load_version("WORKTREE")
        d = next(x for x in reg.docs.values() if x.kind == "規約")
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / "src"
            src.mkdir()
            (src / "okugaki.txt").write_text("証する。\n\n組合\n理事長　氏名\n", encoding="utf-8")
            out = Path(t) / "a.docx"
            build_docx(reg, d, out, src_dir=src, revisions=REVS)
            doc = Document(str(out))
            text = "\n".join(p.text for p in doc.paragraphs)
            self.assertIn(endmatter.HISTORY_TITLE, text)
            self.assertIn("理事長　氏名", text)
            self.assertTrue(any(c.text == "・管理規約 改定" for tb in doc.tables for row in tb.rows for c in row.cells))
            build_docx(reg, d, out, src_dir=src)                                  # 改訂履歴を渡さなければ付かない
            self.assertNotIn(endmatter.HISTORY_TITLE, "\n".join(p.text for p in Document(str(out)).paragraphs))

    def test_mdedit(self):
        reg = load_version("WORKTREE")
        did = next(iter(reg.docs))
        self.assertEqual(mdedit.file_for_node(f"{did}|x", reg, reg.src_dir), Path(reg.docs[did].path))
        self.assertEqual(mdedit.file_for_node("@sign", reg, "S").name, "okugaki.txt")
        self.assertIsNone(mdedit.resolve_editor(""))
        self.assertIsNone(mdedit.resolve_editor(r"Z:\なし\x.exe"))
        self.assertEqual(mdedit.resolve_editor(sys.executable), sys.executable)
        with self.assertRaises(OSError):
            mdedit.open_file(Path("存在しない.md"))


if __name__ == "__main__":
    unittest.main()

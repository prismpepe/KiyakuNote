"""別表・別紙・別図の編集（表のセル・画像の差し替え・新設・削除）の確認。小さな規約を一時フォルダに作って試す。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kiyakunote import appendix_edit as ae  # noqa: E402
from kiyakunote.core import Registry, load_dir  # noqa: E402
from kiyakunote.lint import lint  # noqa: E402
from kiyakunote.tables import list_tables  # noqa: E402

KIYAKU = """---
doc: kiyaku
kind: 規約
title: テスト規約
short: 規約
numbering: renumber
appendices: [tbl-1:1, tbl-2:2, app-1:1]
---

# {#ch-1} 総則

## {#art-001} 目的

1. {#art-001-p1} 別表第1と{ref:tbl-1}を見る。
"""
TBL1 = "---\ndoc: tbl-1\nkind: 別表\ntitle: 範囲\nparent: kiyaku\n---\n\n前置き\n\n| 区分 | 範囲 |\n|------|------|\n| 建物 | 廊下 |\n"
TBL2 = ("---\ndoc: tbl-2\nkind: 別表\ntitle: 持分\nparent: kiyaku\n---\n\n"
        "<table><tr><th>号室</th><th>持分</th></tr>\n<tr><td>101</td><td>10<br>分</td></tr></table>\n")
APP1 = "---\ndoc: app-1\nkind: 別紙\ntitle: 様式\nparent: kiyaku\n---\n\n![様式](assets/old.png)\n"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a5f50000000049454e44ae426082")


class AppendixEditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Path(self.tmp.name) / "src"
        (self.src / "assets").mkdir(parents=True)
        for n, t in (("kiyaku", KIYAKU), ("tbl-1", TBL1), ("tbl-2", TBL2), ("app-1", APP1)):
            (self.src / f"{n}.md").write_text(t, encoding="utf-8", newline="\n")
        (self.src / "assets" / "old.png").write_bytes(PNG)
        self.png = Path(self.tmp.name) / "new image.png"
        self.png.write_bytes(PNG)

    def tearDown(self):
        self.tmp.cleanup()

    def reg(self):
        return Registry(load_dir(self.src))

    def errors(self):
        return [f for f in lint(self.reg()) if f[0] == "E"]

    def test_save_markdown_and_html_tables(self):
        self.assertEqual(self.errors(), [])
        t = list_tables(self.reg().docs["tbl-1"].raw_body)[0]
        rows = t["rows"] + [["敷地", "駐車場<br>駐輪場"]]
        ae.save_table(self.src / "tbl-1.md", 0, rows)
        body = self.reg().docs["tbl-1"].raw_body
        self.assertIn("前置き", body)                                        # 表の外の文章は変わらない
        self.assertEqual(list_tables(body)[0]["rows"][-1], ["敷地", "駐車場\n駐輪場"])
        t2 = list_tables(self.reg().docs["tbl-2"].raw_body)[0]
        rows2 = [r[:] for r in t2["rows"]]
        rows2[1][1] = "20"
        ae.save_table(self.src / "tbl-2.md", 0, rows2)
        b2 = self.reg().docs["tbl-2"].raw_body
        self.assertIn("<th>号室</th>", b2)                                  # HTMLの表は HTML のまま・1行目は th
        self.assertEqual(list_tables(b2)[0]["rows"][1], ["101", "20"])
        self.assertEqual(self.errors(), [])

    def test_replace_image_keeps_old_file(self):
        name = ae.replace_image(self.src / "app-1.md", 0, self.png)
        self.assertTrue((self.src / "assets" / name).exists())
        self.assertTrue((self.src / "assets" / "old.png").exists())
        self.assertIn(f"assets/{name}", self.reg().docs["app-1"].raw_body)
        with self.assertRaises(ae.AppendixError):
            ae.replace_image(self.src / "tbl-1.md", 0, self.png)           # 画像のない文書
        with self.assertRaises(ae.AppendixError):
            ae.replace_image(self.src / "app-1.md", 0, Path(self.tmp.name) / "a.txt")

    def test_create_and_delete(self):
        reg = self.reg()
        path, ppath, old = ae.create_appendix(reg, "kiyaku", "別表", "新しい表", ncols=3, nrows=4)
        r2 = self.reg()
        d = r2.docs[path.stem]
        self.assertEqual(r2.appendix_no(d), 3)                               # 別表は 1,2 の次で 3
        self.assertEqual(len(list_tables(d.raw_body)[0]["rows"]), 4)
        self.assertEqual(self.errors(), [])
        p2, _, _ = ae.create_appendix(r2, "kiyaku", "別紙", "新しい様式", image_file=self.png)
        r3 = self.reg()
        self.assertEqual(r3.appendix_no(r3.docs[p2.stem]), 2)                # 別紙は 1 の次で 2
        self.assertIn("assets/", r3.docs[p2.stem].raw_body)
        ae.delete_appendix(self.src / "tbl-1.md")
        r4 = self.reg()
        self.assertEqual(r4.docs["tbl-1"].meta.get("deleted"), "true")
        self.assertEqual(r4.appendix_no(r4.docs[path.stem]), 3)              # 削除しても番号は詰めない
        with self.assertRaises(ae.AppendixError):
            ae.delete_appendix(self.src / "tbl-1.md")
        ppath.write_bytes(old)                                               # 親の元の内容に戻せる
        self.assertNotIn(path.stem, self.reg().docs["kiyaku"].meta["appendices"][-1])


if __name__ == "__main__":
    unittest.main()

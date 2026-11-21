"""別表・別紙の表の解析（画面で罫線つきの表にするため）。結合セルを保つ。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kiyakunote.gui_table import parse_md_table, parse_table, plain_text, split_body  # noqa: E402


class TableParseTest(unittest.TestCase):
    def test_spans_and_br(self):
        html = ('<table><tr><th colspan="2">タイプ</th><th>面積</th></tr>'
                '<tr><td rowspan="2">住戸</td><td>A1</td><td>80.69<br>㎡</td></tr>'
                '<tr><td>A2</td><td>80.69</td></tr></table>')
        cells = {(r, c): (rs, cs, t) for r, c, rs, cs, t, _ in parse_table(html)}
        self.assertEqual(cells[(0, 0)][:2], (1, 2))                 # 見出しは2列にまたがる
        self.assertEqual(cells[(0, 2)][2], "面積")
        self.assertEqual(cells[(1, 0)][:2], (2, 1))                 # 「住戸」は2行にまたがる
        self.assertEqual(cells[(1, 2)][2], "80.69\n㎡")             # <br> は改行
        self.assertEqual(cells[(2, 1)][2], "A2")                     # 結合セルの下は列がずれない

    def test_split_body(self):
        parts = split_body("（１）駐車場使用料\n\n<table><tr><td>a</td></tr></table>\n\n※注")
        self.assertEqual([k for k, _ in parts], ["text", "table", "text"])
        self.assertEqual(plain_text("<b>x</b><br>y"), "x\ny")

    def test_markdown_table(self):
        body = "前置き\n\n| 区分 | 範囲 |\n|------|------|\n| 共用 | 廊下<br>階段 |\n\n注記"
        parts = split_body(body)
        self.assertEqual([k for k, _ in parts], ["text", "mdtable", "text"])
        cells = {(r, c): (t, th) for r, c, _, _, t, th in parse_md_table(parts[1][1])}
        self.assertEqual(cells[(0, 0)], ("区分", True))               # 1行目は見出し
        self.assertEqual(cells[(1, 1)], ("廊下\n階段", False))        # 区切りの行（---）は表に入れない


if __name__ == "__main__":
    unittest.main()

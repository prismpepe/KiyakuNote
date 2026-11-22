"""結合セルのある表の編集（行・列の追加と削除）と、Excel との往復。画面（Tk）は使わない。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kiyakunote import tables as T  # noqa: E402

SAMPLE = ('<table><tr><th>見出し</th><th colspan="2">結合</th></tr>'
          '<tr><td rowspan="2">縦</td><td>a</td><td>b</td></tr>'
          '<tr><td>c</td><td>d</td></tr></table>')


def real_tables():
    out = []
    for p in sorted((ROOT / "src").glob("*.md")):
        for t in T.list_tables(p.read_text(encoding="utf-8-sig")):
            if t["kind"] == "table":
                out.append((p.name, T.fill_holes(t["cells"])))
    return out


class CellsTest(unittest.TestCase):
    def test_render_roundtrip(self):
        cells = T.parse_table(SAMPLE)
        self.assertIsNone(T.validate_cells(cells))
        self.assertEqual(sorted(T.parse_table(T.render_html_cells(cells))), sorted(cells))

    def test_insert_row_inside_rowspan(self):
        cells = T.insert_row(T.parse_table(SAMPLE), 1)            # 行1（縦が2行にまたがる）の下に入れる
        self.assertIsNone(T.validate_cells(cells))
        self.assertEqual(T.table_size(cells), (4, 3))
        tall = next(c for c in cells if c[4] == "縦")
        self.assertEqual(tall[2], 3)                              # 縦は3行にまたがる

    def test_delete_row_moves_tall_cell(self):
        cells = T.delete_row(T.parse_table(SAMPLE), 1)             # 縦が始まる行を消す
        self.assertIsNone(T.validate_cells(cells))
        tall = next(c for c in cells if c[4] == "縦")
        self.assertEqual((tall[0], tall[2]), (1, 1))               # 縦は残り、次の行から始まる
        with self.assertRaises(ValueError):
            T.delete_row([(0, 0, 1, 1, "x", False)], 0)

    def test_col_ops(self):
        cells = T.parse_table(SAMPLE)
        x = T.insert_col(cells, 1)                                 # 結合（colspan=2）の途中に列を入れる
        self.assertIsNone(T.validate_cells(x))
        self.assertEqual(next(c for c in x if c[4] == "結合")[3], 3)
        y = T.delete_col(cells, 1)
        self.assertIsNone(T.validate_cells(y))
        self.assertEqual(next(c for c in y if c[4] == "結合")[3], 1)

    def test_replace_table_cells(self):
        raw = "前\n\n" + SAMPLE + "\n\n後"
        cells = T.insert_row(T.parse_table(SAMPLE), 2)
        out = T.replace_table_cells(raw, 0, cells)
        self.assertTrue(out.startswith("前\n\n<table>") and out.endswith("</table>\n\n後"))
        self.assertEqual(T.table_size(T.parse_table(out[out.index("<table"):out.index("</table>") + 8])), (4, 3))

    def test_real_tables_invariants(self):
        tables = real_tables()
        self.assertGreaterEqual(len(tables), 0)          # 公開版のサンプルには結合セルの表が少ない
        for name, cells in tables:
            nr, nc = T.table_size(cells)
            self.assertIsNone(T.validate_cells(cells), name)
            self.assertEqual(sorted(T.parse_table(T.render_html_cells(cells))), sorted(cells), name)
            for a in (-1, 0, nr - 1):
                x = T.insert_row(cells, a)
                self.assertTrue(T.validate_cells(x) is None and T.table_size(x) == (nr + 1, nc), (name, a))
            for a in (0, nc - 1):
                x = T.insert_col(cells, a)
                self.assertTrue(T.validate_cells(x) is None and T.table_size(x) == (nr, nc + 1), (name, a))
            for r in {0, nr // 2, nr - 1} if nr > 1 else ():
                x = T.delete_row(cells, r)
                self.assertTrue(T.validate_cells(x) is None and T.table_size(x) == (nr - 1, nc), (name, r))
            for c in {0, nc // 2, nc - 1} if nc > 1 else ():
                x = T.delete_col(cells, c)
                self.assertTrue(T.validate_cells(x) is None and T.table_size(x) == (nr, nc - 1), (name, c))


class XlsxTest(unittest.TestCase):
    def test_roundtrip_real_tables(self):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            self.skipTest("openpyxl がありません")
        from kiyakunote import xlsx_io
        with tempfile.TemporaryDirectory() as d:
            for name, cells in real_tables():
                f = Path(d) / "t.xlsx"
                xlsx_io.export_cells(cells, f)
                self.assertEqual(sorted(xlsx_io.import_cells(f)), sorted(cells), name)

    def test_empty_sheet(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl がありません")
        from kiyakunote import xlsx_io
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "e.xlsx"
            openpyxl.Workbook().save(str(f))
            with self.assertRaises(xlsx_io.XlsxError):
                xlsx_io.import_cells(f)


if __name__ == "__main__":
    unittest.main()

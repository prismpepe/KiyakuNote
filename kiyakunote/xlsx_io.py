"""表と Excel ブックの相互変換（openpyxl）。画面を使わない。

セルの一覧 (行, 列, 行の幅, 列の幅, 文字, 見出しか) ↔ シート。結合セルは Excel の「セルの結合」に対応する。
見出しのセルは太字・薄い青の地で書き出し、取り込むときは太字のセルを見出しとみなす。
"""
import datetime
from pathlib import Path

from .tables import fill_holes, table_size, validate_cells


class XlsxError(Exception):
    pass


def _openpyxl():
    try:
        import openpyxl
    except ImportError as e:                                    # noqa: BLE001
        raise XlsxError("Excel の読み書きには openpyxl が要ります（pip install openpyxl）") from e
    return openpyxl


def export_cells(cells, path, sheet="表"):
    """セルの一覧を Excel ブック（.xlsx）に書く。"""
    ox = _openpyxl()
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    cells = fill_holes(cells)
    wb = ox.Workbook()
    ws = wb.active
    ws.title = sheet
    thin = Side(style="thin", color="888888")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    nrows, ncols = table_size(cells)
    for r, c, rs, cs, text, th in cells:
        for dr in range(rs):
            for dc in range(cs):
                ws.cell(row=r + dr + 1, column=c + dc + 1).border = border       # 結合の範囲全体に罫線
        cell = ws.cell(row=r + 1, column=c + 1, value=text)
        cell.alignment = Alignment(wrap_text=True, vertical="top" if not th else "center", horizontal="center" if th else "left")
        if th:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="DBE5F1")
        if rs > 1 or cs > 1:
            ws.merge_cells(start_row=r + 1, start_column=c + 1, end_row=r + rs, end_column=c + cs)
    for c in range(ncols):
        longest = max((max((len(x) for x in str(cell[4]).split("\n")), default=0) for cell in cells if cell[1] == c and cell[3] == 1), default=8)
        ws.column_dimensions[get_column_letter(c + 1)].width = max(8, min(40, longest * 2 + 2))
    wb.save(str(path))


def _text(v):
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.strftime("%Y-%m-%d")
    return str(v).replace("\r\n", "\n").replace("\r", "\n").strip()


def import_cells(path, sheet=None):
    """Excel ブックのシートを、セルの一覧にする。結合セルは行・列の幅になる。"""
    ox = _openpyxl()
    try:
        wb = ox.load_workbook(str(path), data_only=True)
    except Exception as e:                                      # noqa: BLE001
        raise XlsxError(f"Excel のファイルを読めません: {e}") from e
    ws = wb[sheet] if sheet else wb.active
    if ws.max_row < 1 or ws.max_column < 1 or all(v is None for row in ws.iter_rows(values_only=True) for v in row):
        raise XlsxError("シートが空です")
    r0, c0 = ws.min_row, ws.min_column
    merged = {}
    inside = set()
    for rng in ws.merged_cells.ranges:
        merged[(rng.min_row, rng.min_col)] = (rng.max_row - rng.min_row + 1, rng.max_col - rng.min_col + 1)
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                if (r, c) != (rng.min_row, rng.min_col):
                    inside.add((r, c))
    cells = []
    for r in range(r0, ws.max_row + 1):
        for c in range(c0, ws.max_column + 1):
            if (r, c) in inside:
                continue
            cell = ws.cell(row=r, column=c)
            rs, cs = merged.get((r, c), (1, 1))
            cells.append((r - r0, c - c0, rs, cs, _text(cell.value), bool(cell.font and cell.font.bold)))
    err = validate_cells(cells)
    if err:
        raise XlsxError("結合セルを表にできません: " + err)
    return cells

"""別表・別紙の表（HTMLの <table> と、Markdownの | の表）の解析と書き出し。画面を使わない。結合セル（colspan・rowspan）を解析できる。"""
import html
import re
from html.parser import HTMLParser


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.cur, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self.cur = []
        elif tag in ("td", "th") and self.cur is not None:
            self.cell = {"text": "", "cs": int(a.get("colspan") or 1), "rs": int(a.get("rowspan") or 1), "th": tag == "th"}
        elif tag == "br" and self.cell is not None:
            self.cell["text"] += "\n"

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.cur is not None:
            self.cell["text"] = re.sub(r"[ \t\r\f]+", " ", self.cell["text"]).strip()
            self.cur.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.cur is not None:
            self.rows.append(self.cur)
            self.cur = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"] += data.replace("\n", "")


def parse_table(markup):
    """HTMLの表を、(行, 列, 行の幅, 列の幅, 文字, 見出しか) のセルの一覧にする。"""
    p = _Parser()
    p.feed(markup)
    cells, taken = [], set()
    for r, row in enumerate(p.rows):
        c = 0
        for cell in row:
            while (r, c) in taken:
                c += 1
            cells.append((r, c, cell["rs"], cell["cs"], cell["text"], cell["th"]))
            for dr in range(cell["rs"]):
                for dc in range(cell["cs"]):
                    taken.add((r + dr, c + dc))
            c += cell["cs"]
    return cells


MD_ROW = re.compile(r"^\s*\|.*\|\s*$")
MD_SEP = re.compile(r"^\s*\|(\s*:?-+:?\s*\|)+\s*$")         # 区切りの行（|---|---|）。空のセルだけの行とは区別する


def parse_md_table(lines):
    """Markdownの表（| で区切る形）を、parse_table と同じセルの一覧にする。1行目は見出し。"""
    cells, r = [], 0
    for ln in lines:
        if MD_SEP.match(ln):
            continue
        parts = [c.strip().replace("<br>", "\n") for c in ln.strip().strip("|").split("|")]
        for c, text in enumerate(parts):
            cells.append((r, c, 1, 1, text, r == 0))
        r += 1
    return cells


def _pieces(raw):
    """本文を (種類, 中身, 元の文字) に分ける。元の文字をつなぐと、本文にぴったり戻る。"""
    out, pos = [], 0
    for m in re.finditer(r"<table.*?</table>", raw, re.S):
        out.extend(_pieces_md(raw[pos:m.start()]))
        out.append(("table", m.group(0), m.group(0)))
        pos = m.end()
    out.extend(_pieces_md(raw[pos:]))
    return out


def _pieces_md(text):
    out, buf, tab = [], [], []

    def flush(kind, lines):
        if lines:
            out.append((kind, [x.rstrip("\r\n") for x in lines] if kind == "mdtable" else "".join(lines), "".join(lines)))

    for ln in text.splitlines(keepends=True):
        if MD_ROW.match(ln.rstrip("\r\n")):
            flush("text", buf)
            buf = []
            tab.append(ln)
        else:
            flush("mdtable", tab)
            tab = []
            buf.append(ln)
    flush("mdtable", tab)
    flush("text", buf)
    return out


def split_body(raw):
    """本文を、文章と表の並び [("text", 文字) / ("table", html) / ("mdtable", 行のリスト)] に分ける。"""
    return [(k, p) for k, p, _ in _pieces(raw)]


def plain_text(s):
    s = re.sub(r"<br\s*/?>", "\n", s)
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip("\n")


# ---- 編集用: 結合セルのない表を、行と列の一覧にして書き戻す ----
def has_span(cells):
    return any(rs > 1 or cs > 1 for _, _, rs, cs, _, _ in cells)


def cells_to_rows(cells):
    """セルの一覧を、行×列の文字の一覧にする（結合セルがないときだけ使える）。"""
    nrows = max((r + 1 for r, *_ in cells), default=0)
    ncols = max((c + 1 for _, c, *_ in cells), default=0)
    rows = [["" for _ in range(ncols)] for _ in range(nrows)]
    for r, c, _, _, text, _ in cells:
        rows[r][c] = text
    return rows


def md_cell(s):
    return s.replace("|", "｜").replace("\r", "").replace("\n", "<br>").strip()


def render_md_table(rows):
    """1行目を見出しとする Markdown の表。"""
    if not rows:
        return ""
    w = max(len(r) for r in rows)
    rows = [list(r) + [""] * (w - len(r)) for r in rows]
    out = ["| " + " | ".join(md_cell(c) for c in rows[0]) + " |", "|" + "|".join(["------"] * w) + "|"]
    out += ["| " + " | ".join(md_cell(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(out)


def render_html_table(rows, header_rows=1):
    """HTMLの表（1行目を th にする）。実データの別表の書式にそろえる。"""
    w = max((len(r) for r in rows), default=0)
    lines = []
    for i, r in enumerate(rows):
        tag = "th" if i < header_rows else "td"
        cells = "".join(f"<{tag}>{html.escape(c, quote=False).replace(chr(10), '<br>')}</{tag}>" for c in list(r) + [""] * (w - len(r)))
        lines.append(f"<tr>{cells}</tr>")
    return "<table>" + "\n".join(lines) + "\n</table>"


def list_tables(raw_body):
    """本文の中の表を、順に [{kind: 'table'|'mdtable', cells, rows, span}] にする。"""
    out = []
    for kind, chunk in split_body(raw_body):
        if kind == "table":
            cells = parse_table(chunk)
        elif kind == "mdtable":
            cells = parse_md_table(chunk)
        else:
            continue
        out.append({"kind": kind, "cells": cells, "span": has_span(cells), "rows": None if has_span(cells) else cells_to_rows(cells)})
    return out


def _replace_nth(raw_body, index, make):
    """本文の index 番目の表を、make(種類, 元の中身) の返す文字に置き換える。それ以外は元のまま（改行も含めてぴったり保つ）。"""
    out, n = [], -1
    for kind, payload, rawtext in _pieces(raw_body):
        if kind in ("table", "mdtable"):
            n += 1
            if n == index:
                new = make(kind, payload)
                if kind == "mdtable" and rawtext.endswith("\n"):
                    new += "\r\n" if rawtext.endswith("\r\n") else "\n"
                out.append(new)
                continue
        out.append(rawtext)
    if n < index:
        raise IndexError("表がありません")
    return "".join(out)


def replace_table(raw_body, index, rows):
    """本文の index 番目の表を、rows で置き換えた本文を返す（表の形式 Markdown / HTML は元のまま。表の外は変えない）。"""
    def make(kind, payload):
        if kind == "table":
            return render_html_table(rows, 1 if re.search(r"<tr>\s*<th", payload) else 0)
        return render_md_table(rows)
    return _replace_nth(raw_body, index, make)


# ---- 結合セルのある表の編集（セルの一覧 (行, 列, 行の幅, 列の幅, 文字, 見出しか) のまま扱う）----
def table_size(cells):
    """(行数, 列数)。"""
    return (max((r + rs for r, _, rs, _, _, _ in cells), default=0),
            max((c + cs for _, c, _, cs, _, _ in cells), default=0))


def validate_cells(cells):
    """セルが格子に重なりなく、すき間なく並んでいるか。問題があれば説明の文字、なければ None。"""
    nrows, ncols = table_size(cells)
    seen = {}
    for i, (r, c, rs, cs, *_rest) in enumerate(cells):
        if rs < 1 or cs < 1:
            return "セルの幅が正しくありません"
        for dr in range(rs):
            for dc in range(cs):
                if (r + dr, c + dc) in seen:
                    return f"セルが重なっています（{r + dr + 1}行{c + dc + 1}列）"
                seen[(r + dr, c + dc)] = i
    for r in range(nrows):
        for c in range(ncols):
            if (r, c) not in seen:
                return f"セルのない所があります（{r + 1}行{c + 1}列）"
    return None


def render_html_cells(cells):
    """結合セルを保ったまま HTML の表にする（実データの別表の書式: <tr>…</tr> を改行でつなぐ）。"""
    nrows, _ = table_size(cells)
    rows = [[] for _ in range(nrows)]
    for cell in sorted(cells, key=lambda x: (x[0], x[1])):
        rows[cell[0]].append(cell)
    lines = []
    for row in rows:
        out = []
        for _, _, rs, cs, text, th in row:
            tag = "th" if th else "td"
            attr = (f' rowspan="{rs}"' if rs > 1 else "") + (f' colspan="{cs}"' if cs > 1 else "")
            out.append(f"<{tag}{attr}>{html.escape(text, quote=False).replace(chr(10), '<br>')}</{tag}>")
        lines.append("<tr>" + "".join(out) + "</tr>")
    return "<table>" + "\n".join(lines) + "\n</table>"


def _transpose(cells):
    return [(c, r, cs, rs, t, th) for r, c, rs, cs, t, th in cells]


def insert_row(cells, after, header=False):
    """行 after（0始まり）の次に空の行を入れる。after=-1 なら先頭。またがっているセルは、その分だけ高くなる。"""
    p = after + 1
    nrows, ncols = table_size(cells)
    out, covered = [], set()
    for r, c, rs, cs, t, th in cells:
        if r >= p:
            out.append((r + 1, c, rs, cs, t, th))
        elif r + rs > p:                                  # 入れる位置をまたぐセル
            out.append((r, c, rs + 1, cs, t, th))
            covered.update(range(c, c + cs))
        else:
            out.append((r, c, rs, cs, t, th))
    out += [(p, c, 1, 1, "", header) for c in range(ncols) if c not in covered]
    return out


def delete_row(cells, r):
    """行 r を消す。その行から始まる高いセルは、次の行から始まる（文字は残す）。最後の1行は消せない。"""
    nrows, _ = table_size(cells)
    if nrows <= 1:
        raise ValueError("1行だけになるので、削除できません")
    out = []
    for r0, c, rs, cs, t, th in cells:
        if r0 > r:
            out.append((r0 - 1, c, rs, cs, t, th))
        elif r0 <= r < r0 + rs:
            if rs > 1:
                out.append((r0, c, rs - 1, cs, t, th))      # 行が1つ減る（始まりの行なら、次の行が新しい始まり）
        else:
            out.append((r0, c, rs, cs, t, th))
    return out


def insert_col(cells, after):
    """列 after の次に空の列を入れる。新しいセルは、左隣のセルが見出しなら見出しにする。"""
    out = _transpose(insert_row(_transpose(cells), after))
    p = after + 1
    left = {(r, c): th for r, c, rs, cs, _, th in cells for r in range(r, r + rs) for c in range(c, c + cs)}
    return [(r, c, rs, cs, "", left.get((r, after), False)) if c == p else (r, c, rs, cs, t, th)
            for r, c, rs, cs, t, th in out]


def delete_col(cells, c):
    return _transpose(delete_row(_transpose(cells), c))


def replace_table_cells(raw_body, index, cells):
    """本文の index 番目の表を、結合セルを保ったまま cells で置き換える。Markdown の表は結合できないので、結合があれば HTML にする。"""
    err = validate_cells(cells)
    if err:
        raise ValueError(err)
    return _replace_nth(raw_body, index, lambda kind, _p: render_md_table(cells_to_rows(cells)) if kind == "mdtable" and not has_span(cells)
                        else render_html_cells(cells))


def fill_holes(cells):
    """元の表で、セルが足りない所（行の途中で終わっている等）を、空のセルで埋める。表示は変わらない。"""
    nrows, ncols = table_size(cells)
    taken = {(r + dr, c + dc) for r, c, rs, cs, *_ in cells for dr in range(rs) for dc in range(cs)}
    return list(cells) + [(r, c, 1, 1, "", False) for r in range(nrows) for c in range(ncols) if (r, c) not in taken]


# ---- セルの結合・結合の解除 ----
def _join_text(a, b):
    return "\n".join(x for x in (a, b) if x)


def merge_right(cells, i):
    """i 番目のセルを、右隣のセルと結合する。右隣が同じ高さの1つのセルであるときだけできる。"""
    r, c, rs, cs, t, th = cells[i]
    nxt = [k for k, x in enumerate(cells) if x[0] == r and x[1] == c + cs]
    if not nxt:
        raise ValueError("右にセルがありません")
    r2, c2, rs2, cs2, t2, th2 = cells[nxt[0]]
    if rs2 != rs:
        raise ValueError("右のセルと高さ（行の数）が違うので、結合できません")
    out = [x for k, x in enumerate(cells) if k not in (i, nxt[0])]
    out.append((r, c, rs, cs + cs2, _join_text(t, t2), th or th2))
    return out


def merge_down(cells, i):
    """i 番目のセルを、下のセルと結合する。下が同じ幅の1つのセルであるときだけできる。"""
    r, c, rs, cs, t, th = cells[i]
    nxt = [k for k, x in enumerate(cells) if x[1] == c and x[0] == r + rs]
    if not nxt:
        raise ValueError("下にセルがありません")
    r2, c2, rs2, cs2, t2, th2 = cells[nxt[0]]
    if cs2 != cs:
        raise ValueError("下のセルと幅（列の数）が違うので、結合できません")
    out = [x for k, x in enumerate(cells) if k not in (i, nxt[0])]
    out.append((r, c, rs + rs2, cs, _join_text(t, t2), th or th2))
    return out


def unmerge(cells, i):
    """i 番目のセルの結合を解除する。文字は、行数がセルの数と同じなら1行ずつ各セルへ、そうでなければ左上のセルに残す。"""
    r, c, rs, cs, t, th = cells[i]
    if rs == 1 and cs == 1:
        raise ValueError("このセルは結合されていません")
    out = [x for k, x in enumerate(cells) if k != i]
    lines = t.split("\n")
    spread = len(lines) == rs * cs                            # 結合でつないだ文字（改行区切り）なら、元のセルに振り分ける
    out += [(r + dr, c + dc, 1, 1, lines[dr * cs + dc] if spread else (t if (dr, dc) == (0, 0) else ""), th)
            for dr in range(rs) for dc in range(cs)]
    return out


def unmerge_to(cells, i, parts):
    """i 番目のセルを、結合する前の parts（結合前のセルの一覧。結合した順）に戻す。文字は、行数が parts の数と同じなら1行ずつ、違えば最初のセルに入れる。"""
    r, c, rs, cs, text, th = cells[i]
    lines = text.split(chr(10))
    texts = lines if len(lines) == len(parts) else [text] + [""] * (len(parts) - 1)
    out = [x for k, x in enumerate(cells) if k != i]
    out += [(pr, pc, prs, pcs, tx, pth) for (pr, pc, prs, pcs, _, pth), tx in zip(parts, texts)]
    return out

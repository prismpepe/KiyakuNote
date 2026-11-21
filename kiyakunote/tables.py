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


def split_body(raw):
    """本文を、文章と表の並び [("text", 文字) / ("table", html) / ("mdtable", 行のリスト)] に分ける。"""
    out, pos = [], 0
    for m in re.finditer(r"<table.*?</table>", raw, re.S):
        if m.start() > pos:
            out.extend(_split_md(raw[pos:m.start()]))
        out.append(("table", m.group(0)))
        pos = m.end()
    if pos < len(raw):
        out.extend(_split_md(raw[pos:]))
    return out


def _split_md(text):
    out, buf, tab = [], [], []
    for ln in text.split("\n"):
        if MD_ROW.match(ln):
            if buf:
                out.append(("text", "\n".join(buf)))
                buf = []
            tab.append(ln)
        else:
            if tab:
                out.append(("mdtable", tab))
                tab = []
            buf.append(ln)
    if tab:
        out.append(("mdtable", tab))
    if buf:
        out.append(("text", "\n".join(buf)))
    return out


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


def replace_table(raw_body, index, rows):
    """本文の index 番目の表を、rows で置き換えた本文を返す（表の形式 Markdown / HTML は元のまま。表の外は変えない）。"""
    parts, n = [], -1
    for kind, chunk in split_body(raw_body):
        if kind in ("table", "mdtable"):
            n += 1
            if n == index:
                if kind == "table":
                    hdr = 1 if re.search(r"<tr>\s*<th", chunk) else 0
                    parts.append(render_html_table(rows, hdr))
                else:
                    parts.append(render_md_table(rows))
                continue
            parts.append(chunk if kind == "table" else "\n".join(chunk))
        else:
            parts.append(chunk)
    return "\n".join(parts)

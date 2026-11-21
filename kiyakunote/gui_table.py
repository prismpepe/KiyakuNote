"""別表・別紙の表（HTMLの <table>）を、画面に罫線つきの表として出す。結合セル（colspan・rowspan）に対応する。"""
import html
import re
import tkinter as tk
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
MD_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


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


def table_frame(parent, cells, font, bold_font, on_wheel=None, width=880):
    """罫線のある表（Frame）を作る。1行目などの見出しは太字・色付き。"""
    ncols = max((c + cs for _, c, _, cs, _, _ in cells), default=1)
    wrap = max(70, min(300, width // ncols - 24))              # 列が多い表は、1列を狭くして画面の幅に収める
    fr = tk.Frame(parent, background="#8a8a8a", padx=1, pady=1)          # 外枠の左・上の線
    for r, c, rs, cs, text, th in cells:
        lab = tk.Label(fr, text=text, font=bold_font if th else font, background="#dbe5f1" if th else "#ffffff",
                       foreground="#111111", justify="left" if not th else "center", anchor="nw" if not th else "n",
                       wraplength=wrap, padx=8, pady=4)
        lab.grid(row=r, column=c, rowspan=rs, columnspan=cs, sticky="nsew", padx=(0, 1), pady=(0, 1))
        if on_wheel:
            lab.bind("<MouseWheel>", on_wheel)
    if on_wheel:
        fr.bind("<MouseWheel>", on_wheel)
    return fr

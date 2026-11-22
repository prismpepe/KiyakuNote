"""Word（.docx）出力。規約・細則の本文（番号振り・参照展開済み）と、別表・別紙、新旧対照表を出す。

条文は実際の規約の書式に合わせる: 見出し「（目的）」を条の前の行に、第1項は「第N条　」に続け、
第2項以降は「２　」、号は「（１）　」、細分は「ア．」。別表・別紙の表は結合セルを保つ。
画像（別紙1〜4、別図）はPDFのページ画像をそのまま貼る。
"""
import html
import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from . import endmatter
from .core import Heading, fw
from .render import expand_text, first_referrer, item_numbers, marker, para_display

FONT = "MS 明朝"
SIZE = 10.5
DEFAULT_FONT, DEFAULT_SIZE = FONT, SIZE


def configure(family="", size=0):
    """Word出力の本文のフォントと大きさを変える（空・0 なら従来どおり）。見出しなどの相対的な大きさ・表の幅は変えない。"""
    global FONT, SIZE
    FONT = (family or "").strip() or DEFAULT_FONT
    SIZE = float(size) if size else DEFAULT_SIZE


def new_document(landscape=False, header=""):
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(SIZE)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    if landscape:
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = sec.page_height, sec.page_width
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Cm(2.2))
    if header:
        hp = sec.header.paragraphs[0]
        hp.text = header
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for r in hp.runs:
            r.font.size = Pt(8)
    page_number(sec.footer.paragraphs[0])
    return doc


def page_number(p):
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    for typ, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if typ:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), typ)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)


def set_font(run, size=None, bold=None):
    run.font.name = FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold


def add_text(p, text, size=None, bold=None):
    """改行（\\n）はWordの改行にする。"""
    for i, line in enumerate(text.split("\n")):
        if i:
            p.add_run().add_break()
        r = p.add_run(line)
        set_font(r, size, bold)


def para(doc, text="", align=None, left=0.0, first=0.0, size=None, bold=None, keep=False, before=0, after=3):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Pt(left * SIZE)
    pf.first_line_indent = Pt(first * SIZE)
    pf.space_before, pf.space_after = Pt(before), Pt(after)
    pf.keep_with_next = keep
    if align:
        p.alignment = align
    if text:
        add_text(p, text, size, bold)
    return p


def write_paras(doc, reg, d, art, paras):
    """条（または見出し直下）の項を書く。"""
    counted = 0
    for pi, p in enumerate(paras, 1):
        txt = expand_text(reg, p.text, d, (d, art, pi))
        if p.counted:
            counted += 1
            lead, hang = f"{fw(counted)}．", 1.5
        elif pi == 1:
            lead, hang = "", 0
        else:
            n, b = para_display(art, pi)
            lead, hang = (f"{n}の{b}　" if b else f"{n}　"), 1
        if pi == 1 and art is not None and not p.counted:
            lead, hang = f"{art.label}　", 0
        para(doc, lead + txt, left=hang, first=-hang if hang else 0)
        write_items(doc, reg, d, art, pi, p.items)


def write_items(doc, reg, d, art, pi, items):
    for it, (n, b) in zip(items, item_numbers(items)):
        txt = expand_text(reg, it.text, d, (d, art, pi))
        para(doc, marker(it.level, n, b) + "　" + txt, left=1.5 * it.level + 1, first=-1.5)
        write_items(doc, reg, d, art, pi, it.children)


def write_doc_body(doc, reg, d):
    """1文書の本文（章・節・条）を書く。"""
    para(doc, d.title, WD_ALIGN_PARAGRAPH.CENTER, size=15, bold=True, before=6, after=12)
    for el in d.elements:
        if isinstance(el, Heading):
            if el.kind == "supplementary":
                para(doc, "附　則", WD_ALIGN_PARAGRAPH.CENTER, bold=True, before=12, after=6, keep=True)
            elif el.kind == "section":
                para(doc, f"第{fw(el.number)}節　{el.title}", WD_ALIGN_PARAGRAPH.CENTER, bold=True, before=8, after=4, keep=True)
            elif el.title.strip() != "本則":
                para(doc, f"第{fw(el.number)}章　{el.title}", WD_ALIGN_PARAGRAPH.CENTER, size=12, bold=True, before=12, after=6, keep=True)
            write_paras(doc, reg, d, None, el.paras)
            continue
        if el.deleted:
            para(doc, f"{el.label}　削除", before=6)
            continue
        if el.title:
            para(doc, f"（{el.title}）", before=6, after=1, keep=True)
        write_paras(doc, reg, d, el, el.paras)


# ---- 別表・別紙 ----

class Cell:
    def __init__(self, text, rowspan=1, colspan=1, header=False):
        self.text, self.rowspan, self.colspan, self.header = text, rowspan, colspan, header


def parse_html_table(body):
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S):
        row = []
        for m in re.finditer(r"<(t[dh])((?:\s[^>]*)?)>(.*?)</t[dh]>", tr, re.S):
            attrs = m.group(2)
            rs = re.search(r'rowspan="(\d+)"', attrs)
            cs = re.search(r'colspan="(\d+)"', attrs)
            txt = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", m.group(3)))).strip()
            row.append(Cell(txt, int(rs.group(1)) if rs else 1, int(cs.group(1)) if cs else 1, m.group(1) == "th"))
        rows.append(row)
    return rows


def parse_md_table(lines):
    rows = []
    for ln in lines:
        if re.fullmatch(r"\s*\|?[\s|:\-]+\|?\s*", ln):
            continue
        rows.append([Cell(c.strip()) for c in ln.strip().strip("|").split("|")])
    if rows:
        for c in rows[0]:
            c.header = True
    return rows


def write_table(doc, rows, size=8.5):
    """結合セルを保って表を書く。行・列の占有を格子で追う。"""
    ncols, occupied = 0, set()
    placed = []
    for r, row in enumerate(rows):
        c = 0
        for cell in row:
            while (r, c) in occupied:
                c += 1
            for dr in range(cell.rowspan):
                for dc in range(cell.colspan):
                    occupied.add((r + dr, c + dc))
            placed.append((r, c, cell))
            c += cell.colspan
        ncols = max(ncols, c)
    nrows = max(r + cl.rowspan for r, _, cl in placed) if placed else 0
    table = doc.add_table(rows=nrows, cols=ncols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # 列の幅は、各列の文字数（結合していないセル）に比例させる
    weight = [4.0] * ncols
    for r, c, cell in placed:
        if cell.colspan == 1:
            longest = max((len(x) for x in cell.text.splitlines()), default=0)
            weight[c] = max(weight[c], min(longest, 40) + 4)
    total_w = sum(weight)
    table.autofit = False
    widths = [Cm(16.6 * w / total_w) for w in weight]
    for r, c, cell in placed:
        r2, c2 = min(r + cell.rowspan - 1, nrows - 1), min(c + cell.colspan - 1, ncols - 1)
        target = table.cell(r, c)
        if (r2, c2) != (r, c):
            target = target.merge(table.cell(r2, c2))
        target.text = ""
        if cell.colspan == 1:
            target.width = widths[c]
        p = target.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        add_text(p, cell.text, size, bold=True if cell.header else None)
        if cell.header:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return table


def write_appendix(doc, reg, parent, app, src_dir):
    n = reg.appendix_no(app)
    label = "別図" if app.kind == "別図" else (f"別表第{n}" if app.kind == "別表" else f"{app.kind}{n}")
    doc.add_page_break()
    if app.meta.get("deleted") == "true":
        para(doc, f"{label}（削除）", bold=True)
        return
    ref = first_referrer(reg, parent, app)
    rel = f"（{ref.label}関係）" if ref else ""
    para(doc, f"{label}{rel}　{app.title}", bold=True, size=12, after=6, keep=True)
    body = app.raw_body
    if "<table" in body:
        pos = 0
        for m in re.finditer(r"<table.*?</table>", body, re.S):
            for t in re.split(r"\n\s*\n", body[pos:m.start()]):
                if t.strip():
                    para(doc, html.unescape(re.sub(r"<[^>]+>", "", t)).strip())
            write_table(doc, parse_html_table(m.group(0)))
            pos = m.end()
        for t in re.split(r"\n\s*\n", body[pos:]):
            if t.strip():
                para(doc, html.unescape(re.sub(r"<[^>]+>", "", t)).strip())
        return
    lines = body.splitlines()
    buf = []
    for ln in lines + [""]:
        if ln.strip().startswith("|"):
            buf.append(ln)
            continue
        if buf:
            write_table(doc, parse_md_table(buf))
            buf = []
        m = re.match(r"!\[[^\]]*\]\(([^)]+)\)", ln.strip())
        if m:
            img = Path(src_dir) / m.group(1)
            if img.exists():
                doc.add_picture(str(img), width=Cm(15.5))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                para(doc, f"（画像が見つからない: {m.group(1)}）")
        elif ln.strip():
            para(doc, ln.strip())


def write_history(doc, revs):
    """改訂履歴の表。"""
    para(doc, endmatter.HISTORY_TITLE, bold=True, size=12, after=6, keep=True)
    rows = endmatter.history_rows(revs)
    write_table(doc, [[Cell(txt, header=(i == 0)) for txt in row] for i, row in enumerate(rows)])


def write_signature(doc, src_dir):
    """理事長の署名（奥書）。無ければ何も書かない。"""
    sign = endmatter.load_okugaki(src_dir)
    if sign:
        para(doc, "", after=12)
        for i, s in enumerate(sign):
            last = i == len(sign) - 1
            for ln in s.split("\n"):
                para(doc, ln, align=WD_ALIGN_PARAGRAPH.RIGHT if i > 0 else None, after=2 if not last else 0)
            para(doc, "", after=6)


def write_endmatter(doc, revs, src_dir):
    """巻末: 改訂履歴の表と、理事長の署名（奥書）。"""
    if revs:
        doc.add_page_break()
        write_history(doc, revs)
    write_signature(doc, src_dir)


def build_docx(reg, d, path, src_dir="src", revisions=None):
    """文書 d を、その別表・別紙・別図を付けて .docx に書く。規約には、巻末に改訂履歴と署名（奥書）も付ける。"""
    doc = new_document(header=d.title)
    write_doc_body(doc, reg, d)
    for ent in d.meta.get("appendices", []):
        app = reg.docs.get(ent.partition(":")[0])
        if app:
            write_appendix(doc, reg, d, app, src_dir)
    if d.kind == "規約":
        write_endmatter(doc, revisions, src_dir)
    doc.save(str(path))


# ---- 新旧対照表 ----

MARK = re.compile(r"(~~.*?~~|\*\*.*?\*\*)", re.S)


def add_marked(p, text, size=8.5):
    """~~削除~~ は赤の取消線、**追加** は青の太字・下線で書く。"""
    for part in MARK.split(text):
        if not part:
            continue
        if part.startswith("~~") and part.endswith("~~") and len(part) > 4:
            seg, style = part[2:-2], "del"
        elif part.startswith("**") and part.endswith("**") and len(part) > 4:
            seg, style = part[2:-2], "ins"
        else:
            seg, style = part, None
        for i, line in enumerate(seg.split("\n")):
            if i:
                p.add_run().add_break()
            r = p.add_run(line)
            set_font(r, size)
            if style == "del":
                r.font.strike = True
                r.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
            elif style == "ins":
                r.bold = True
                r.underline = True
                r.font.color.rgb = RGBColor(0x00, 0x32, 0xA0)


def build_compare_docx(reg_old, reg_new, label_old, label_new, path, notes=None):
    from .compare import compare_doc, appendix_changes, KINDS
    doc = new_document(landscape=True, header="新旧対照表")
    para(doc, "新旧対照表", WD_ALIGN_PARAGRAPH.CENTER, size=15, bold=True, after=6)
    para(doc, f"改正前: {label_old}")
    para(doc, f"改正後: {label_new}", after=8)
    ids = [i for i, d in reg_new.docs.items() if d.kind not in ("別表", "別紙", "別図")]
    ids += [i for i in reg_old.docs if i not in ids and reg_old.docs[i].kind not in ("別表", "別紙", "別図")]
    total = {k: 0 for k in KINDS}
    for did in ids:
        rows = compare_doc(reg_old, reg_new, did)
        if not rows:
            continue
        d = reg_new.docs.get(did) or reg_old.docs[did]
        para(doc, d.title, bold=True, size=12, before=10, keep=True)
        t = doc.add_table(rows=1, cols=3)
        t.style = "Table Grid"
        for c, h in zip(t.rows[0].cells, ("区分", "改正前", "改正後")):
            c.text = ""
            add_text(c.paragraphs[0], h, 9, True)
            c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        for kind, to, tn in rows:
            total[kind] += 1
            cells = t.add_row().cells
            cells[0].text = ""
            add_text(cells[0].paragraphs[0], kind, 8.5)
            for c, txt in ((cells[1], to), (cells[2], tn)):
                c.text = ""
                add_marked(c.paragraphs[0], txt)
        for row in t.rows:
            row.cells[0].width, row.cells[1].width, row.cells[2].width = Cm(2.6), Cm(11.6), Cm(11.6)
    ap = appendix_changes(reg_old, reg_new)
    if ap:
        para(doc, "別表・別紙・別図", bold=True, size=12, before=10)
        for i, tt, k in ap:
            para(doc, f"{tt}（{i}）　{k}")
    summary = "、".join(f"{k} {v}件" for k, v in total.items() if v) or "変更なし"
    para(doc, f"変更: {summary}", before=8)
    if notes:
        para(doc, "要確認: IDに変換されていない参照", bold=True, size=12, before=10, keep=True)
        para(doc, f"次の {len(notes)} 件は本文に番号を直書きしたままで、条番号が変わっても自動では更新されない。"
                  "改正で番号が動く場合は、参照先が合っているか人が確認する。")
        for n in notes[:80]:
            para(doc, "・" + n, size=9, after=1)
        if len(notes) > 80:
            para(doc, f"・ほか {len(notes) - 80} 件", size=9)
    doc.save(str(path))


# ---- 冊子（一冊の管理規約） ----

def set_outline(p, level):
    """段落に、目次に載る見出しレベル（1〜）を付ける。"""
    ppr = p._p.get_or_add_pPr()
    el = OxmlElement("w:outlineLvl")
    el.set(qn("w:val"), str(level - 1))
    ppr.append(el)


def start_part(doc, header=""):
    """新しいページ（セクション）を始め、そのページのヘッダーの文字を決める。"""
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    sec.header.is_linked_to_previous = False
    hp = sec.header.paragraphs[0]
    hp.text = header
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for r in hp.runs:
        r.font.size = Pt(8)
    return sec


def field_paragraphs(doc, instr, cached):
    """複数の段落にまたがるフィールド（目次）を書く。cached は、更新前に見せる [(レベル, 文字)]。"""
    paras = []
    for lv, text in cached:
        paras.append(para(doc, text, left=(lv - 1) * 1.5, bold=True if lv == 1 else None, before=4 if lv == 1 else 0, after=1))
    if not paras:
        return

    def fld(p, typ=None, text=None, first=False):
        run = p.add_run()
        el = OxmlElement("w:fldChar" if typ else "w:instrText")
        if typ:
            el.set(qn("w:fldCharType"), typ)
        else:
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)
        if first:
            p._p.remove(run._r)
            p._p.insert(1 if p._p.pPr is not None else 0, run._r)

    first = paras[0]
    # 先頭の段落の、文字の前に「開始・命令・区切り」を入れる（逆順に先頭へ差し込む）
    for typ, text in (("separate", None), (None, instr), ("begin", None)):
        fld(first, typ, text, first=True)
    fld(paras[-1], "end")


def build_book(reg, plan, path, src_dir="src", revisions=None, title=""):
    """冊子の構成 plan（book.parse_book の結果）に従って、一冊の .docx を書く。"""
    docs = reg.docs
    doc = new_document(header="")
    toc = []
    for key, val in plan:
        if key == "中表紙":
            toc.append((1, val))
        elif key == "文書" and val in docs:
            toc.append((2, docs[val].title))
        elif key == "改訂履歴":
            toc.append((1, endmatter.HISTORY_TITLE))
    cover = [v for k, v in plan if k == "表紙"]
    first_part, prev = True, None
    for n, line in enumerate(cover):
        para(doc, line, WD_ALIGN_PARAGRAPH.CENTER, size=26 if n == 0 else 14, bold=True if n == 0 else None,
             before=230 if n == 0 else 0, after=20 if n == 0 else 8)
    first_part = not cover                                        # 表紙があれば、最初の項目は新しいページから
    for key, val in plan:
        if key == "目次":
            if not first_part:
                start_part(doc, "")
            first_part = False
            para(doc, "目　次", WD_ALIGN_PARAGRAPH.CENTER, size=15, bold=True, before=6, after=12)
            field_paragraphs(doc, 'TOC \\u \\h \\z', toc)
        elif key == "中表紙":
            if not first_part:
                start_part(doc, "")
            first_part = False
            p = para(doc, val, WD_ALIGN_PARAGRAPH.CENTER, size=28, bold=True, before=250)
            set_outline(p, 1)
        elif key == "文書":
            d = docs[val]
            if not first_part:
                start_part(doc, d.title)
            first_part = False
            n0 = len(doc.paragraphs)
            write_doc_body(doc, reg, d)
            set_outline(doc.paragraphs[n0], 2)
        elif key == "別表等":
            d = docs[val]
            for ent in d.meta.get("appendices", []):
                app = reg.docs.get(ent.partition(":")[0])
                if app:
                    write_appendix(doc, reg, d, app, src_dir)
        elif key == "改訂履歴":
            if revisions:
                if not first_part:
                    start_part(doc, endmatter.HISTORY_TITLE)
                first_part = False
                n0 = len(doc.paragraphs)
                write_history(doc, revisions)
                set_outline(doc.paragraphs[n0], 1)
        elif key == "署名":
            if prev != "改訂履歴" or not revisions:
                if not first_part:
                    start_part(doc, "")
                first_part = False
            write_signature(doc, src_dir)
        prev = key
    doc.save(str(path))

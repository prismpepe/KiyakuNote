"""検索索引（SQLite FTS5）。正本から作る使い捨ての派生物で、壊れたら作り直す。

- 項・号・条の見出しごとに1行。本文は参照を展開した出力どおりの文字（番号も計算した値）。
- 日本語は単語に分けず、FTS5 の trigram（3文字以上の部分一致）で引く。1〜2文字の語は LIKE で引く。
- 全角・半角はNFKCで揃えて索引・検索する（表示は原文のまま）。
- 参照の表（refs）から、「この条を参照している条」（参照元）と「この条が参照している条」（参照先）を引ける。
"""
import html
import re
import sqlite3
import unicodedata
from pathlib import Path

from .core import Heading, Loc, APPENDIX_KINDS
from .render import TOKEN, abs_label, expand_text, parse_ref, resolve_one, RefError

SCHEMA = """
create table nodes(
  id integer primary key, ord integer, doc text, doc_title text, kind text,
  node_id text, article_id text, level text, label text, art_title text,
  text text, ntext text);
create virtual table fts using fts5(ntext, tokenize='trigram');
create table refs(
  from_doc text, from_id text, from_article text, from_label text,
  to_doc text, to_id text, to_article text, to_label text);
create table meta(key text primary key, value text);
"""


def norm(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def doc_order(d):
    return (0 if d.id == "kiyaku" else 1 if d.id.startswith("bylaw") and "-app" not in d.id else 2, d.id)


def plain(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", s))


class Indexer:
    def __init__(self, reg, con):
        self.reg, self.con, self.n = reg, con, 0

    def add(self, doc, ordn, node_id, art_id, level, label, art_title, text, raw=None, src=None):
        self.n += 1
        self.con.execute("insert into nodes values(?,?,?,?,?,?,?,?,?,?,?,?)",
                         (self.n, ordn, doc.id, doc.title, doc.kind, node_id, art_id, level, label,
                          art_title, text, norm(f"{label} {art_title} {text}")))
        self.con.execute("insert into fts(rowid, ntext) values(?,?)",
                         (self.n, norm(f"{label} {art_title} {text}")))
        if raw:
            self.add_refs(doc, node_id or art_id, art_id, label, raw, src)

    def add_refs(self, doc, from_id, from_article, from_label, raw, src):
        for m in TOKEN.finditer(raw):
            if m.group(1) != "ref":
                continue
            target, opts = parse_ref(m.group(2))
            for t in re.split(r",|\.\.", target):
                try:
                    loc = resolve_one(self.reg, t.strip(), doc.id)
                except RefError:
                    continue
                tid = t.strip().split("#")[-1]
                art = loc.article.id if loc.article is not None else ""
                self.con.execute("insert into refs values(?,?,?,?,?,?,?,?)",
                                 (doc.id, from_id, from_article, from_label, loc.doc.id, tid, art,
                                  abs_label(loc, self.reg, doc, {"as": loc.doc.short} if loc.doc.id != doc.id else {})))

    def doc(self, doc, ordn):
        reg = self.reg
        if doc.kind in APPENDIX_KINDS:
            n = reg.appendix_no(doc)
            label = "別図" if doc.kind == "別図" else (f"別表第{n}" if doc.kind == "別表" else f"別紙{n}")
            self.add(doc, ordn, doc.id, "", "appendix", label, doc.title, "")
            if "<tr" in doc.raw_body:
                for tr in re.findall(r"<tr>(.*?)</tr>", doc.raw_body, re.S):
                    cells = [plain(c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
                    self.add(doc, ordn, doc.id, "", "appendix", label, doc.title, " | ".join(c for c in cells if c))
            else:                                   # Markdown の表・段落（画像の行は除く）
                for ln in doc.raw_body.splitlines():
                    ln = ln.strip()
                    if not ln or ln.startswith("!") or re.fullmatch(r"[|\-: ]+", ln):
                        continue
                    cells = [c.strip() for c in ln.strip("|").split("|")]
                    self.add(doc, ordn, doc.id, "", "appendix", label, doc.title, " | ".join(c for c in cells if c))
            return
        for el in doc.elements:
            if isinstance(el, Heading):
                continue
            label = el.label
            if el.deleted:
                self.add(doc, ordn, el.id, el.id, "article", label, el.title, "削除")
                continue
            self.add(doc, ordn, el.id, el.id, "article", label, el.title, "")
            for pi, p in enumerate(el.paras, 1):
                loc = Loc(doc, "para", el, pi)
                plabel = abs_label(loc, reg, doc, {}) if len(el.paras) > 1 else label
                txt = expand_text(reg, p.text, doc, (doc, el, pi))
                self.add(doc, ordn, p.id or el.id, el.id, "para", plabel, el.title, txt, p.text)
                self.items(doc, ordn, el, pi, p.items, ())

    def items(self, doc, ordn, art, pi, items, path):
        for ii, it in enumerate(items, 1):
            pth = path + (ii,)
            loc = Loc(doc, "item", art, pi, pth)
            label = abs_label(loc, self.reg, doc, {"p": True})
            txt = expand_text(self.reg, it.text, doc, (doc, art, pi)).replace("\n", " ")
            self.add(doc, ordn, it.id or art.id, art.id, "item", label, art.title, txt, it.text)
            self.items(doc, ordn, art, pi, it.children, pth)


def build_index(reg, db_path):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(str(db_path))
    con.executescript(SCHEMA)
    ix = Indexer(reg, con)
    for ordn, d in enumerate(sorted(reg.docs.values(), key=doc_order)):
        ix.doc(d, ordn)
    con.commit()
    con.close()
    return ix.n


def search(db_path, query, doc=None, kind=None, level=None, limit=50):
    """空白区切りの語をすべて含む行を返す。3文字以上はFTS（部分一致）、1〜2文字はLIKE。"""
    con = sqlite3.connect(str(db_path))
    where, args = [], []
    terms = norm(query).split(" ")
    for t in [t for t in terms if t]:
        if len(t) >= 3:
            where.append("id in (select rowid from fts where fts match ?)")
            args.append('"' + t.replace('"', '""') + '"')
        else:
            where.append("ntext like ? escape '\\'")
            args.append("%" + t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if doc:
        where.append("doc = ?")
        args.append(doc)
    if kind:
        where.append("kind = ?")
        args.append(kind)
    if level:
        where.append("level = ?")
        args.append(level)
    sql = ("select doc_title, doc, label, art_title, text, level, node_id from nodes "
           + ("where " + " and ".join(where) if where else "") + " order by ord, id limit ?")
    rows = con.execute(sql, args + [limit]).fetchall()
    con.close()
    return rows


def snippet(text, query, width=40):
    t = norm(text)
    terms = [x for x in norm(query).split(" ") if x]
    for term in terms:
        i = t.find(term)
        if i >= 0:
            s = max(0, i - width)
            return ("…" if s else "") + t[s:i] + "【" + t[i:i + len(term)] + "】" + t[i + len(term):i + len(term) + width] + ("…" if len(t) > i + len(term) + width else "")
    return t[:width * 2]


def refs_of(db_path, ident):
    """ident は 'id' または 'doc#id'。(参照先, 参照元) を返す。"""
    con = sqlite3.connect(str(db_path))
    doc, _, nid = ident.rpartition("#")
    q = " and doc = ?" if doc else ""
    base = ([nid] + ([doc] if doc else []))
    art = con.execute("select article_id from nodes where node_id = ?" + q, base).fetchone()
    art_id = art[0] if art else nid
    out = con.execute("select from_label, to_doc, to_label from refs where from_id in "
                      "(select node_id from nodes where article_id = ?" + q + ")", [art_id] + ([doc] if doc else [])).fetchall()
    inc = con.execute("select from_doc, from_label, to_label from refs where to_article = ? and from_article != to_article"
                      + (" and to_doc = ?" if doc else ""),
                      [art_id] + ([doc] if doc else [])).fetchall()
    con.close()
    return out, inc

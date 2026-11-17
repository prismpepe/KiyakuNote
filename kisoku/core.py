"""正本（Markdown）の解析と、番号振り・IDの登録。"""
import re
from dataclasses import dataclass, field
from pathlib import Path

FW = str.maketrans("0123456789", "０１２３４５６７８９")
APPENDIX_KINDS = ("別表", "別紙", "別図")


def fw(n):
    """全角数字にする。"""
    return str(n).translate(FW)


@dataclass
class Item:
    id: str
    text: str
    level: int = 1            # 1=号, 2=号の細分(ア．), 3=（ア）
    children: list = field(default_factory=list)
    line: int = 0
    branch: bool = False      # 号の枝番（直前の号の「の２」）


@dataclass
class Para:
    id: str
    text: str
    items: list = field(default_factory=list)
    line: int = 0
    counted: bool = False     # 附則の「１．」形式の項
    branch: bool = False      # 項の枝番（直前の項の「の２」。「４の２」）


@dataclass
class Heading:
    id: str
    title: str
    flags: set
    paras: list = field(default_factory=list)
    line: int = 0
    kind: str = "chapter"     # chapter | section | supplementary（番号振りの結果）
    number: int = 0


@dataclass
class Article:
    id: str
    title: str
    flags: set
    paras: list = field(default_factory=list)
    line: int = 0
    deleted: bool = False
    branch: bool = False
    # 以下は番号振りの結果
    supplementary: bool = False
    number: int = 0
    branch_no: int = 0
    index: int = 0            # 同じ番号体系（本則／附則）の中での通し位置

    @property
    def label(self):
        s = f"第{self.number}条"
        if self.branch_no:
            s += f"の{self.branch_no}"
        return ("附則" if self.supplementary else "") + s


@dataclass
class Doc:
    id: str
    meta: dict
    elements: list            # Heading | Article の並び
    path: str = ""
    articles: list = field(default_factory=list)
    raw_body: str = ""        # 別表・別紙・別図の本体

    @property
    def kind(self):
        return self.meta.get("kind", "")

    @property
    def short(self):
        return self.meta.get("short") or self.meta.get("title") or self.id

    @property
    def title(self):
        return self.meta.get("title", self.id)


@dataclass
class Loc:
    """IDが指す位置。"""
    doc: Doc
    kind: str                 # article | para | item | heading
    article: object = None
    para: int = 0             # 1始まり
    items: tuple = ()         # 号の位置（1始まり）の並び
    heading: object = None
    deleted: bool = False


class ParseError(Exception):
    pass


def parse_front(text):
    """先頭の --- ... --- を読む。簡易YAML（key: value、[a, b]）のみ。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ParseError("front matter がない")
    meta = {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
        ln = lines[i].split(" #")[0].rstrip()
        if not ln.strip():
            continue
        k, _, v = ln.partition(":")
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        meta[k.strip()] = v
    if end is None:
        raise ParseError("front matter が閉じていない")
    return meta, lines[end + 1:], end + 1


HEAD = re.compile(r"^(#{1,2})\s+(?:\{#([\w.-]+)([^}]*)\}\s*)?(.*?)\s*$")
LIST = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
IDTOK = re.compile(r"^\{#([\w.-]+)((?:\s+\w+)*)\}\s*")


def _take_id(text):
    m = IDTOK.match(text)
    if m:
        return m.group(1), text[m.end():], set(m.group(2).split())
    return "", text, set()


def parse_doc(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    meta, lines, offset = parse_front(text)
    doc = Doc(id=meta.get("doc", ""), meta=meta, elements=[], path=str(path))
    if not doc.id:
        raise ParseError(f"{path}: doc がない")
    if doc.kind in APPENDIX_KINDS:
        doc.raw_body = "\n".join(lines).strip("\n")
        return doc
    cur = None
    stack = []                # 現在のリスト階層 [Para, Item, ...]
    plain = []
    plain_line = 0

    def flush_plain():
        nonlocal plain
        if plain and cur is not None:
            t = "\n".join(plain)
            pid, t, cnt = _take_id(t)
            cur.paras.append(Para(pid, t, [], plain_line, "counted" in cnt, "branch" in cnt))
        plain = []

    for n, raw in enumerate(lines, start=offset + 1):
        m = HEAD.match(raw)
        if m:
            flush_plain()
            stack = []
            hashes, hid, flagtxt, title = m.groups()
            flags = set(flagtxt.split())
            dm = re.search(r"\s*\{deleted\}\s*$", title)
            if dm:
                flags.add("deleted")
                title = title[:dm.start()]
            if len(hashes) == 1:
                cur = Heading(hid or "", title, flags, line=n)
            else:
                cur = Article(hid or "", title, flags, line=n,
                              deleted="deleted" in flags, branch="branch" in flags)
            doc.elements.append(cur)
            continue
        if cur is None:
            if raw.strip():
                raise ParseError(f"{path}:{n}: 見出しの前に本文がある")
            continue
        lm = LIST.match(raw)
        if lm:
            flush_plain()
            level = len(lm.group(1).replace("\t", "   ")) // 3
            node_id, t, cnt = _take_id(lm.group(3))
            if level == 0:
                p = Para(node_id, t, [], n, "counted" in cnt, "branch" in cnt)
                cur.paras.append(p)
                stack = [p]
            else:
                if len(stack) < level:
                    raise ParseError(f"{path}:{n}: 項の下でない号がある")
                parent = stack[level - 1]
                it = Item(node_id, t, level, [], n, "branch" in cnt)
                (parent.items if isinstance(parent, Para) else parent.children).append(it)
                stack = stack[:level] + [it]
            continue
        if not raw.strip():
            flush_plain()
            continue
        if stack:                       # 直前の項・号の続き
            stack[-1].text += "\n" + raw.strip()
        else:
            if not plain:
                plain_line = n
            plain.append(raw.strip())
    flush_plain()
    return doc


def assign_numbers(doc):
    """章・条・附則の番号を振る。枝番は直前の本条に続く。"""
    ch = sec = art = 0
    supp = False
    last = None
    idx = 0
    doc.articles = []
    for el in doc.elements:
        if isinstance(el, Heading):
            if "supplementary" in el.flags:
                el.kind = "supplementary"
                supp, art, last, idx = True, 0, None, 0
            elif "section" in el.flags:
                el.kind = "section"
                sec += 1
                el.number = sec
            else:
                el.kind = "chapter"
                supp = False
                ch += 1
                sec = 0
                el.number = ch
            continue
        el.supplementary = supp
        idx += 1
        el.index = idx
        if el.branch and last is not None:
            el.number = last.number
            el.branch_no = max(last.branch_no, 1) + 1   # 第4条の次は「第4条の2」
        else:
            art += 1
            el.number = art
        last = el
        doc.articles.append(el)


class Registry:
    """全文書のIDを登録し、位置を引く。"""

    def __init__(self, docs):
        self.docs = {}
        self.ids = {}             # (doc.id, id) -> Loc
        self.problems = []        # (code, message, doc_id, line)
        for d in docs:
            if d.id in self.docs:
                self.problems.append(("E-DUP-DOC", f"文書IDが重複: {d.id}", d.id, 0))
            self.docs[d.id] = d
            if d.kind not in APPENDIX_KINDS:
                assign_numbers(d)
                self._register(d)

    def _add(self, doc, id_, loc, line):
        if not id_:
            return
        key = (doc.id, id_)
        if key in self.ids:
            self.problems.append(("E-DUP-ID", f"IDが重複: {id_}", doc.id, line))
        else:
            self.ids[key] = loc

    def _register(self, doc):
        for el in doc.elements:
            if isinstance(el, Heading):
                self._add(doc, el.id, Loc(doc, "heading", heading=el), el.line)
                for pi, p in enumerate(el.paras, 1):
                    self._add(doc, p.id, Loc(doc, "heading", heading=el, para=pi), p.line)
                continue
            self._add(doc, el.id, Loc(doc, "article", article=el, deleted=el.deleted), el.line)
            for pi, p in enumerate(el.paras, 1):
                self._add(doc, p.id, Loc(doc, "para", el, pi, deleted=el.deleted), p.line)
                self._items(doc, el, pi, p.items, ())

    def _items(self, doc, art, pi, items, path):
        for ii, it in enumerate(items, 1):
            p = path + (ii,)
            self._add(doc, it.id, Loc(doc, "item", art, pi, p, deleted=art.deleted), it.line)
            self._items(doc, art, pi, it.children, p)

    def find(self, doc_id, id_):
        return self.ids.get((doc_id, id_))

    def appendix_no(self, doc):
        """別表・別紙の番号。親文書の appendices の並び（id:番号 で明示可）から求める。"""
        parent = self.docs.get(doc.meta.get("parent", ""))
        if not parent:
            return None
        n = 0
        for ent in parent.meta.get("appendices", []):
            eid, _, num = ent.partition(":")
            n = int(num) if num else n + 1
            if eid == doc.id:
                return n
        return None


def load_dir(root):
    docs = []
    for p in sorted(Path(root).rglob("*.md")):
        try:
            head = p.read_text(encoding="utf-8-sig")[:4]
        except Exception:
            continue
        if head.startswith("---"):
            docs.append(parse_doc(p))
    return docs


def dump_doc(doc):
    """文書をMarkdownに書き戻す（参照の自動変換などの後処理用）。"""
    head = ["---"]
    for k, v in doc.meta.items():
        head.append(f"{k}: [{', '.join(v)}]" if isinstance(v, list) else f"{k}: {v}")
    head += ["---", ""]
    out = []

    def node(indent, node_id, flags, text):
        tok = "{#" + node_id + "".join(" " + f for f in flags) + "} " if node_id else ""
        first, *rest = text.split("\n")
        out.append(" " * (3 * indent) + "1. " + tok + first)
        for r in rest:
            out.append(" " * (3 * indent + 3) + r)

    def items(lst, indent):
        for it in lst:
            node(indent, it.id, ["branch"] if it.branch else [], it.text)
            items(it.children, indent + 1)

    def paras(lst):
        for p in lst:
            node(0, p.id, (["counted"] if p.counted else []) + (["branch"] if p.branch else []), p.text)
            items(p.items, 1)

    for el in doc.elements:
        out.append("")
        flags = "".join(" " + f for f in sorted(el.flags - {"deleted"}))
        dele = " {deleted}" if isinstance(el, Article) and el.deleted else ""
        mark = "#" if isinstance(el, Heading) else "##"
        idtok = "{#" + el.id + flags + "} " if el.id else ""
        out.append(f"{mark} {idtok}{el.title}{dele}")
        if el.paras:
            out.append("")
        paras(el.paras)
    return "\n".join(head + out).rstrip() + "\n"

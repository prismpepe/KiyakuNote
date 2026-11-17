"""本文に直書きされた参照（第３項・同条第５項・前２項・次条 など）を {ref:…} に書き換える。

書き換えても、出力される文字は変わらない（番号は出力時に計算されるので、条の追加・削除に追随するようになる）。
書き換えないもの（警告として返す）:
- 「…」の中（他の条文を引用した読み替え）
- 前号・次号・本条（相対で、条番号が動いても壊れない）
- 対象が見つからないもの、「同条」の指す先が決められないもの
python -m kiyakunote.idify [src] [--doc kiyaku] [--dry]
"""
import re
import sys
import unicodedata
from pathlib import Path

from .core import Article, Registry, dump_doc, load_dir
from .render import TOKEN, resolve_one

N = r"[0-9０-９]+"
SEP = re.compile(r"^(?:、|から|および|及び|または|又は|ならびに|並びに|もしくは|若しくは)*$")
CHAIN = re.compile(rf"^((?:、第{N}項)*)および第({N})項")          # 直前の {ref} に続く「、第３項、第５項および第６項」
LOCLIST = re.compile(rf"(?<![条法項号0-9０-９])第({N})項(?:、第{N}項)*および第{N}項")   # 同じ条の「第１項および第２項」
PAT = re.compile(
    rf"(?P<same>同条(?:第(?P<sp>{N})項)?(?:第(?P<sk>{N})号)?)"
    rf"|(?P<prev>前(?P<pn>{N})項)"
    rf"|(?P<next>次条(?:第(?P<np>{N})項)?(?:第(?P<nk>{N})号)?)"
    rf"|(?P<loc>(?<![条法項号0-9０-９])第(?P<lp>{N})項(?:第(?P<lk>{N})号)?)")


def num(s):
    return int(unicodedata.normalize("NFKC", s))


class Idifier:
    def __init__(self, reg, doc):
        self.reg, self.doc = reg, doc
        self.warns = []
        self.count = 0

    def exists(self, i):
        return self.reg.find(self.doc.id, i) is not None

    def warn(self, art, why, text):
        self.warns.append((self.doc.id, art.label if art else "", why, text))

    def ctx_of(self, body):
        """{ref:…} の最後の対象の (条ID, 項, 号)。同条・列挙の手がかり。"""
        target = body.split("|")[0].split(",")[-1].split("..")[-1].strip()
        try:
            loc = resolve_one(self.reg, target, self.doc.id)
        except Exception:                                       # noqa: BLE001
            return None
        if loc.article is None or loc.doc.id != self.doc.id:
            return None
        return (loc.article.id, loc.para or None)

    def convert(self, art, pi, text):
        """1つの項・号の本文を変換して返す。"""
        parts = TOKEN.split(text)                 # [平文, 種類, 中身, 平文, 種類, 中身, ..., 平文]
        out = []
        ctx = None
        depth = 0
        prev_tok = None                           # 直前の要素が単純な {ref:X} のとき、out 中の位置と中身
        for i in range(0, len(parts), 3):
            seg = parts[i]
            # 直前の {ref} に続く列挙を、その参照にまとめる
            if prev_tok is not None and depth == 0:
                m = CHAIN.match(seg)
                if m:
                    idx, body = prev_tok
                    cid = self.ctx_of(body)
                    nums = [num(x) for x in re.findall(N, m.group(0))]
                    ids = [f"{cid[0]}-p{n}" for n in nums] if cid else []
                    if cid and all(self.exists(x) for x in ids):
                        out[idx] = "{ref:" + ",".join([body] + ids) + "}"
                        self.count += len(ids)
                        seg = seg[m.end():]
                        prev_tok = None
            piece, depth = self.plain(art, pi, seg, ctx, depth, i > 0)
            out.append(piece)
            ctx = self._last_ctx(out, ctx)
            prev_tok = None
            if i + 2 < len(parts):
                kind, body = parts[i + 1], parts[i + 2]
                out.append("{" + kind + ":" + body + "}")
                if kind == "ref" and depth == 0:          # 「」の中の参照は、引用なので文脈にしない
                    c = self.ctx_of(body)
                    if c:
                        ctx = c
                    if "|" not in body and "," not in body and ".." not in body:
                        prev_tok = (len(out) - 1, body)
        return "".join(out)

    def _last_ctx(self, out, ctx):
        return ctx

    def plain(self, art, pi, s, ctx, depth, after_token=False):
        """平文を変換する。(変換後の文字列, 「」の深さ) を返す。"""
        res = []
        pos = 0
        skip_until = 0
        # 同じ条の列挙（第１項および第２項）を先に1つの参照にする
        spans = []
        for m in LOCLIST.finditer(s):
            spans.append((m.start(), m.end(), m))
        matches = sorted([(m.start(), m.end(), "list", m) for _, _, m in spans] +
                         [(m.start(), m.end(), "pat", m) for m in PAT.finditer(s)], key=lambda x: (x[0], -x[1]))
        chain_art = ctx[0] if (after_token and ctx) else None      # 列挙の続きが指す条（直前の参照の条）
        for start, end, kind, m in matches:
            if start < pos:
                continue
            gap = s[pos:start]
            for ch in gap:
                depth += (ch == "「") - (ch == "」")
            if chain_art is not None and not SEP.match(gap):
                chain_art = None
            new = None
            if depth == 0:
                base = chain_art if chain_art else (art.id if art is not None else None)
                is_loc = kind == "list" or bool(m.group("loc"))
                new = self.list_ref(art, pi, m, base) if kind == "list" else self.make(art, pi, m, ctx, base)
                if isinstance(new, tuple):
                    new, ctx = new
                if new is not None and is_loc and chain_art is None:
                    chain_art = art.id if art is not None else None
                if new is None or not is_loc:
                    chain_art = None
            res.append(s[pos:start])
            res.append(new if new is not None else s[start:end])
            for ch in s[start:end]:
                depth += (ch == "「") - (ch == "」")
            pos = end
        for ch in s[pos:]:
            depth += (ch == "「") - (ch == "」")
        res.append(s[pos:])
        return "".join(res), depth

    def list_ref(self, art, pi, m, base):
        if base is None:
            return None
        nums = [num(x) for x in re.findall(N, m.group(0))]
        ids = [f"{base}-p{n}" for n in nums]
        if not all(self.exists(i) for i in ids):
            self.warn(art, "参照先が存在しない: " + ",".join(ids), m.group(0))
            return None
        self.count += len(ids)
        return "{ref:" + ",".join(ids) + "|local}"

    def make(self, art, pi, m, ctx, base=None):
        if m.group("same"):
            if ctx is None:
                self.warn(art, "「同条」の指す先が決められない", m.group(0))
                return None
            cid, cp = ctx
            sp, sk = m.group("sp"), m.group("sk")
            if sp:
                tid, opt = f"{cid}-p{num(sp)}" + (f"-i{num(sk)}" if sk else ""), "same"
            elif sk:
                tid, opt = f"{cid}-p{cp or 1}-i{num(sk)}", "same,nop"
            else:
                tid, opt = cid, "same"
            if not self.exists(tid):
                self.warn(art, f"参照先が存在しない: {tid}", m.group(0))
                return None
            self.count += 1
            return ("{ref:" + tid + "|" + opt.replace(",", "|") + "}", (cid, num(sp) if sp else cp))
        if m.group("prev"):
            n = num(m.group("pn"))
            if art is None or n < 2 or pi - n < 1:
                return None
            a, b = f"{art.id}-p{pi - n}", f"{art.id}-p{pi - 1}"
            if not (self.exists(a) and self.exists(b)):
                return None
            self.count += 1
            return "{ref:" + a + ".." + b + "|rel}"
        if m.group("next"):
            if art is None or art.index >= len(self.doc.articles) or art.supplementary:
                return None
            nxt = self.doc.articles[art.index]               # index は1始まり。次の条の添字は index
            if nxt.deleted or not nxt.id:
                return None
            tid = nxt.id
            if m.group("np"):
                tid += f"-p{num(m.group('np'))}" + (f"-i{num(m.group('nk'))}" if m.group("nk") else "")
            elif m.group("nk"):
                return None
            if not self.exists(tid):
                self.warn(art, f"参照先が存在しない: {tid}", m.group(0))
                return None
            self.count += 1
            return "{ref:" + tid + "|rel}"
        if m.group("loc"):
            if base is None:
                return None
            p, k = num(m.group("lp")), m.group("lk")
            tid = f"{base}-p{p}" + (f"-i{num(k)}" if k else "")
            if not self.exists(tid):
                self.warn(art, f"参照先が存在しない: {tid}", m.group(0))
                return None
            self.count += 1
            return "{ref:" + tid + "|local}"
        return None


def run(doc, reg):
    """doc の本文を書き換える。(件数, 警告) を返す。"""
    idf = Idifier(reg, doc)
    for el in doc.elements:
        if not isinstance(el, Article) or el.supplementary:
            continue
        for pi, p in enumerate(el.paras, 1):
            p.text = idf.convert(el, pi, p.text)
            stack = list(p.items)
            while stack:
                it = stack.pop()
                it.text = idf.convert(el, pi, it.text)
                stack.extend(it.children)
    return idf.count, idf.warns


def main(argv=None):
    from .core import parse_doc
    args = argv if argv is not None else sys.argv[1:]
    dry = "--dry" in args
    args = [a for a in args if a != "--dry"]
    root = Path(args[0]) if args and not args[0].startswith("--") else Path("src")
    doc_id = "kiyaku"
    if "--doc" in args:
        doc_id = args[args.index("--doc") + 1]
    reg = Registry(load_dir(root))
    d = parse_doc(reg.docs[doc_id].path)
    from .core import assign_numbers
    assign_numbers(d)
    count, warns = run(d, reg)
    print(f"{doc_id}: {count} 件を参照に書き換え、書き換えなかった {len(warns)} 件")
    for w in warns:
        print("  ", w)
    if not dry:
        Path(d.path).write_text(dump_doc(d), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

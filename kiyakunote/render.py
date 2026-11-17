"""参照の展開とMarkdown出力。"""
import re
from .core import Article, Heading, Loc, fw, APPENDIX_KINDS

TOKEN = re.compile(r"\{(ref|ext):([^}]*)\}")
KANA = "アイウエオカキクケコサシスセソタチツテトナニヌネノ"
KANA_P = "ア イ ウ エ オ カ キ ク ケ コ".split()


class RefError(Exception):
    pass


def parse_ref(body):
    """'a|rel|as=X' を (対象リスト, オプション辞書) にする。"""
    parts = body.split("|")
    opts = {}
    for o in parts[1:]:
        k, _, v = o.partition("=")
        opts[k.strip()] = v if _ else True
    return parts[0].strip(), opts


def split_target(t, cur_doc):
    """'doc#id' または 'id' を (doc_id, id) にする。文書IDだけなら id は空。"""
    if "#" in t:
        d, _, i = t.partition("#")
        return d, i
    return cur_doc, t


def resolve_one(reg, target, cur_doc):
    """対象文字列からLocまたは文書を返す。見つからなければ RefError。"""
    d, i = split_target(target, cur_doc)
    loc = reg.find(d, i)
    if loc:
        return loc
    # 同じ文書で見つからないとき、id が文書IDそのもの（別表・別紙）か探す
    if i in reg.docs and reg.docs[i].kind in APPENDIX_KINDS:
        return Loc(reg.docs[i], "doc", deleted=reg.docs[i].meta.get("deleted") == "true")
    if d in reg.docs and not i:
        return Loc(reg.docs[d], "doc")
    raise RefError(f"参照先が存在しない: {target}")


def item_numbers(items):
    """号の並びの表示番号 [(番号, 枝番)]。枝番の号（「(3)の2」）は直前の号と同じ番号で、枝番は2から。"""
    out, n, b = [], 0, 0
    for it in items:
        if getattr(it, "branch", False) and n:
            b += 1
            out.append((n, b + 1))
        else:
            n += 1
            b = 0
            out.append((n, 0))
    return out


def item_label(path, loc=None):
    """号の位置から「第２号」「第２号の２」「第２号ア」を作る。locがあれば、枝番の号を考慮する。"""
    nums = None
    if loc is not None and loc.article is not None and 1 <= loc.para <= len(loc.article.paras):
        nums, lst = [], loc.article.paras[loc.para - 1].items
        for idx in path:
            if idx > len(lst):
                nums = None
                break
            nums.append(item_numbers(lst)[idx - 1])
            lst = lst[idx - 1].children
    first = nums[0] if nums else (path[0], 0)
    s = f"第{fw(first[0])}号" + (f"の{fw(first[1])}" if first[1] else "")
    for lv, n in enumerate(path[1:], 2):
        k = KANA[n - 1] if n <= len(KANA) else str(n)
        s += k if lv == 2 else f"（{k}）"
    return s


def para_display(art, para):
    """項の表示番号 (番号, 枝番)。枝番の項（「４の２」）は直前の項と同じ番号で、枝番は2から。附則の「１．」形式は通し番号。"""
    if art is None or not (1 <= para <= len(art.paras)):
        return para, 0
    if art.paras[para - 1].counted:
        return sum(1 for q in art.paras[:para] if q.counted), 0
    n, b = 0, 0
    for p in art.paras[:para]:
        if p.counted:
            continue
        if p.branch and n:
            b += 1
        else:
            n += 1
            b = 0
    return n, (b + 1 if b else 0)


def para_txt(art, para):
    n, b = para_display(art, para)
    return f"第{n}項" + (f"の{fw(b)}" if b else "")


def para_no(art, para):
    """項の表示番号。附則の「１．」形式（counted）の項は、その中での通し番号。"""
    if art is not None and 1 <= para <= len(art.paras) and art.paras[para - 1].counted:
        return sum(1 for p in art.paras[:para] if p.counted)
    return para


def paras_of(loc):
    return loc.article.paras if loc.article is not None else []


def abs_label(loc, reg, src_doc, opts):
    """絶対番号の表記。他の文書の参照には文書の呼び名を付ける。"""
    d = loc.doc
    if loc.kind == "doc":                # 別表・別紙
        n = reg.appendix_no(d)
        if d.kind == "別図":
            return "別図"
        return f"{d.kind}第{n}" if d.kind == "別表" else f"{d.kind}{n}"
    if loc.kind == "heading":
        base = "附則" if loc.heading.kind == "supplementary" else loc.heading.title
    else:
        a = loc.article
        base = a.label
        if loc.kind in ("para", "item") and (len(a.paras) > 1 or opts.get("p")):
            base += para_txt(a, loc.para)
        if loc.kind == "item":
            base += item_label(loc.items, loc)
    if d.id != src_doc.id:
        base = opts.get("as", d.short) + base
    elif "self" in opts:
        base = opts["self"] + base
    return base


def rel_label(loc, src):
    """前条・前項・次条・次項への言い換え。できなければ None。src=(doc, article, para)。"""
    sdoc, sart, spara = src[:3]
    if loc.doc.id != sdoc.id or loc.article is None or sart is None:
        return None
    t = loc.article
    tail = ""
    if loc.kind == "item":
        tail = item_label(loc.items, loc)
    if t is sart and spara and loc.kind in ("para", "item"):
        if loc.para == spara - 1:
            return "前項" + tail
        if loc.para == spara + 1:
            return "次項" + tail
        return None
    if t.supplementary != sart.supplementary:
        return None
    ptxt = ""
    if loc.kind in ("para", "item") and len(t.paras) > 1:
        ptxt = para_txt(t, loc.para)
    if t.index == sart.index - 1:
        return "前条" + ptxt + tail
    if t.index == sart.index + 1:
        return "次条" + ptxt + tail
    return None


def part_label(loc, nop=False):
    """条の番号を除いた、項・号の部分（「第3項第１号」）。条そのものを指すなら空。
    1項しかない条では項を出さない。nop=True なら項を出さない（「同条第５号」）。"""
    if loc.kind not in ("para", "item"):
        return ""
    s = "" if nop or len(loc.article.paras) <= 1 else para_txt(loc.article, loc.para)
    if loc.kind == "item":
        s += item_label(loc.items, loc)
    return s


def local_label(loc, src, nop=False):
    """同じ条の中の参照（「第3項第１号」）。別の条なら None。"""
    sart = src[1]
    if loc.article is None or sart is None or loc.article is not sart or loc.doc.id != src[0].id:
        return None
    return part_label(loc, nop) or None


def join_labels(labels):
    if len(labels) <= 1:
        return "".join(labels)
    return "、".join(labels[:-1]) + "および" + labels[-1]


def expand_ref(reg, body, cur_doc, src, state=None):
    """{ref:…} の中身を番号に展開する。

    オプション: rel=前条・前項・次条など / title=条名つき / as=・self=文書の呼び名 / p=1項だけの条でも第1項を出す /
    local=同じ条の中なら条を省いて「第3項」/ same=直前に出した参照と同じ条なら「同条第5項」。
    範囲 a..b に rel を付けると、直前の項までなら「前２項」。複数の対象（a,b,c）は同じ条なら「第17条第2項、第3項および第5項」。
    """
    state = state if state is not None else {}
    target, opts = parse_ref(body)
    doc = src[0]
    if ".." in target:
        a, b = [x.strip() for x in target.split("..", 1)]
        la_loc, lb_loc = resolve_one(reg, a, cur_doc.id), resolve_one(reg, b, cur_doc.id)
        if ("rel" in opts and la_loc.kind == lb_loc.kind == "para" and la_loc.article is lb_loc.article
                and la_loc.article is src[1] and src[2] and lb_loc.para == src[2] - 1 and la_loc.para <= lb_loc.para):
            n = lb_loc.para - la_loc.para + 1
            return "前項" if n == 1 else f"前{fw(n)}項"
        if "local" in opts and la_loc.article is lb_loc.article and part_label(la_loc) and part_label(lb_loc) and \
                (la_loc.article is src[1] or la_loc.article is state.get("art")):
            return f"{part_label(la_loc)}から{part_label(lb_loc)}まで"      # 同じ条の中の範囲（第5項から第7項まで）
        la = abs_label(la_loc, reg, doc, opts)
        lb = abs_label(lb_loc, reg, doc, {})
        if la_loc.article is not src[1] and not state.get("quoted"):
            state["art"] = la_loc.article
        return f"{la}から{lb}まで"
    locs = [resolve_one(reg, t.strip(), cur_doc.id) for t in target.split(",") if t.strip()]
    labels = []
    for k, loc in enumerate(locs):
        lab = None
        if k > 0 and loc.article is not None and loc.article is locs[0].article                 and loc.kind in ("para", "item") and locs[0].kind in ("para", "item"):
            lab = part_label(loc)                  # 同じ条の2つ目以降は条を省く（前条第4項および第5項）
        if lab is None and "rel" in opts:
            lab = rel_label(loc, src)
        if lab is None and "same" in opts and loc.article is not None and loc.article is state.get("art"):
            lab = "同条" + part_label(loc, nop="nop" in opts)
        if lab is None and "local" in opts:
            lab = local_label(loc, src, "nop" in opts)
            if lab is None and loc.article is not None and loc.article is state.get("art") and part_label(loc, "nop" in opts):
                lab = part_label(loc, "nop" in opts)             # 直前に出した参照と同じ条なら、条を省く
        if lab is None and k > 0 and loc.article is not None and loc.article is locs[0].article \
                and loc.kind in ("para", "item") and locs[0].kind in ("para", "item"):
            lab = part_label(loc)                  # 同じ条の2つ目以降は条を省く
        if lab is None:
            lab = abs_label(loc, reg, doc, opts)
        if "title" in opts and loc.kind == "article":
            lab += f"（{loc.article.title}）"
        labels.append(lab)
    # 「同条」の指す先は、本文中で最後に引いた別の条。同じ条の中の項への参照や、「」の中の引用では動かさない
    if locs and locs[-1].article is not src[1] and not state.get("quoted"):
        state["art"] = locs[-1].article
    return join_labels(labels)


def expand_text(reg, text, cur_doc, src):
    state = {}

    def sub(m):
        if m.group(1) == "ext":
            return m.group(2).strip()
        before = text[:m.start()]
        state["quoted"] = before.count("「") > before.count("」")
        return expand_ref(reg, m.group(2), cur_doc, src, state)
    return TOKEN.sub(sub, text)


def marker(level, n, b=0):
    if level == 1:
        return f"（{fw(n)}）" + (f"の{fw(b)}" if b else "")
    k = KANA[n - 1] if n <= len(KANA) else str(n)
    return f"{k}．" if level == 2 else f"（{k}）"


def item_lines(reg, items, cur_doc, src):
    out = []
    for it, (n, b) in zip(items, item_numbers(items)):
        txt = expand_text(reg, it.text, cur_doc, src).replace("\n", "　")
        out.append(" " * it.level + marker(it.level, n, b) + "　" + txt)
        out += item_lines(reg, it.children, cur_doc, src)
    return out


def render_paras(reg, paras, cur_doc, art, blocks):
    """項を出力する。第1項は番号なし、第2項以降は「２　」。"""
    counted = 0
    for pi, p in enumerate(paras, 1):
        txt = expand_text(reg, p.text, cur_doc, (cur_doc, art, pi))
        if p.counted:
            counted += 1
            head = f"{fw(counted)}．{txt}"
        else:
            n, b = para_display(art, pi)
            head = txt if pi == 1 else (f"{n}の{b}　{txt}" if b else f"{n}　{txt}")
        blocks.append(head)
        if p.items:
            blocks.append("\n".join(item_lines(reg, p.items, cur_doc, (cur_doc, art, pi))))


def render_doc(reg, doc, title_level=1):
    blocks = [f"# {doc.title}"]
    in_section = False
    for el in doc.elements:
        if isinstance(el, Heading):
            in_section = el.kind == "section"
            if el.kind == "supplementary":
                blocks.append("## 附則")
            elif el.kind == "section":
                blocks.append(f"### 第{el.number}節　{el.title}")
            elif el.title.strip() != "本則":
                blocks.append(f"## 第{el.number}章　{el.title}")
            render_paras(reg, el.paras, doc, None, blocks)
            continue
        h = "####" if in_section else "###"
        if el.deleted:
            blocks.append(f"{h} {el.label}　削除")
            continue
        t = f"（{el.title}）" if el.title else ""
        blocks.append(f"{h} {el.label}{t}")
        render_paras(reg, el.paras, doc, el, blocks)
    blocks += render_appendices(reg, doc)
    return "\n\n".join(blocks) + "\n"


def first_referrer(reg, parent, app_doc):
    """別表を最初に参照している条（「第4条の2関係」の元）。"""
    pat = re.compile(r"\{ref:([^}|]*)")
    def hits(text, art):
        for m in pat.finditer(text):
            for t in re.split(r"[,]|\.\.", m.group(1)):
                t = t.strip()
                d, i = split_target(t, parent.id)
                if i == app_doc.id or d == app_doc.id:
                    return True
        return False
    def walk(items, art):
        for it in items:
            if hits(it.text, art) or walk(it.children, art):
                return True
        return False
    for a in parent.articles:
        for p in a.paras:
            if hits(p.text, a) or walk(p.items, a):
                return a
    return None


def render_appendices(reg, parent):
    out = []
    for ent in parent.meta.get("appendices", []):
        eid = ent.partition(":")[0]
        app = reg.docs.get(eid)
        if not app:
            continue
        n = reg.appendix_no(app)
        label = "別図" if app.kind == "別図" else (
            f"別表第{n}" if app.kind == "別表" else f"{app.kind}{n}")
        if app.meta.get("deleted") == "true":
            out.append(f"## {label}（削除）")
            continue
        ref = first_referrer(reg, parent, app)
        rel = f"（{ref.label}関係）" if ref else ""
        out.append(f"## {label}{rel}　{app.title}")
        out.append(app.raw_body)
    return out


def article_text(reg, doc, art):
    """1つの条を、見出し行つきの本文テキスト（Markdown）にする。新旧対照表で使う。"""
    if art.deleted:
        return f"{art.label}　削除"
    t = f"（{art.title}）" if art.title else ""
    blocks = [f"{art.label}{t}"]
    render_paras(reg, art.paras, doc, art, blocks)
    return "\n".join(blocks)


def article_source(art):
    """参照を展開する前の、条の本文（ID参照のまま）。改正で内容が変わったかの判定に使う。"""
    def items(lst):
        return [(it.text, items(it.children)) for it in lst]
    return (art.title, art.deleted,
            [(p.text, p.counted, items(p.items)) for p in art.paras])

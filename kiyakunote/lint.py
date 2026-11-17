"""整合性チェック。エラーは E-、警告は W- で始まる。"""
import re
from .core import Heading, APPENDIX_KINDS
from .render import TOKEN, parse_ref, resolve_one, RefError, split_target

BARE_REL = re.compile(r"前条|次条|前項|次項|前[２-９0-9]項|前各号|前号|次号|同条|同項|本条")
BARE_NUM = re.compile(r"(?<![\w｀])((?:同法|[^\s、。（）「」]{0,8}法律?)?)第[0-9０-９]+条")


def texts(doc):
    """(行, 条, 本文) を順に返す。"""
    def walk_items(items, art):
        for it in items:
            yield it.line, art, it.text
            yield from walk_items(it.children, art)
    for el in doc.elements:
        art = el if not isinstance(el, Heading) else None
        for p in el.paras:
            yield p.line, art, p.text
            yield from walk_items(p.items, art)


def lint(reg):
    out = []

    def add(sev, code, msg, doc, line):
        out.append((sev, code, msg, doc, line))

    for code, msg, d, line in reg.problems:
        add("E", code, msg, d, line)
    for doc in reg.docs.values():
        if doc.kind in APPENDIX_KINDS:
            if reg.appendix_no(doc) is None:
                add("E", "E-APPENDIX", "親文書の appendices に載っていない別表・別紙", doc.id, 0)
            continue
        for ent in doc.meta.get("appendices", []):
            eid = ent.partition(":")[0]
            if eid not in reg.docs:
                add("E", "E-APPENDIX", f"appendices の文書が存在しない: {eid}", doc.id, 0)
        for el in doc.elements:
            if not isinstance(el, Heading) and not el.id:
                add("W", "W-NOID", f"条にIDがない: {el.label}", doc.id, el.line)
        for line, art, text in texts(doc):
            for m in TOKEN.finditer(text):
                if m.group(1) == "ext":
                    continue
                target, _ = parse_ref(m.group(2))
                for t in re.split(r",|\.\.", target):
                    t = t.strip()
                    try:
                        loc = resolve_one(reg, t, doc.id)
                    except RefError as e:
                        add("E", "E-REF", str(e), doc.id, line)
                        continue
                    if loc.deleted:
                        add("E", "E-DELETED", f"削除済みの条を参照: {t}", doc.id, line)
            bare = TOKEN.sub("", text)
            for m in BARE_REL.finditer(bare):
                add("W", "W-BARE-REL", f"相対参照が文中に直書き: {m.group(0)}", doc.id, line)
            for m in BARE_NUM.finditer(bare):
                if m.group(1):      # 「同法第2条」など外部法令と見なす
                    continue
                add("W", "W-BARE-NUM", f"条番号が文中に直書き: {m.group(0)}", doc.id, line)
    return out

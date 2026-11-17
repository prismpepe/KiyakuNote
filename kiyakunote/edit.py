"""条文の編集（追加・変更・削除）。GUIから使う処理で、画面なしでも試験できる。

編集用のテキストは、1行が1つの項・号で、行頭の語が階層を示す:
    項 {#art-019-p1} 区分所有者は…       （第1項、第2項…）
    号 {#art-019-p5-i1} 契約の相手方が…  （（１）（２）…）
    細 …                                   （ア．イ．…）
    目 …                                   （（ア）（イ）…）
{#…} はIDで、変えない（新しい行は省略すると自動で付く）。語頭のない行は、直前の行の続き（改行）になる。
本文中の {ref:…} は参照。番号は出力時に計算される。
"""
import re
from pathlib import Path

from .core import Article, Item, Para, dump_doc, parse_doc

LEVELS = {"項": 0, "号": 1, "細": 2, "目": 3}
NAMES = {v: k for k, v in LEVELS.items()}
LINE = re.compile(r"^(項|号|細|目)(?:\s+\{#([\w.-]+)((?:\s+\w+)*)\})?\s?(.*)$")


def load_for_edit(path):
    return parse_doc(path)


def find_article(doc, art_id):
    for el in doc.elements:
        if isinstance(el, Article) and el.id == art_id:
            return el
    raise KeyError(art_id)


def article_to_text(art):
    """条の項・号を、編集用のテキストにする。"""
    out = []

    def items(lst, level):
        for it in lst:
            flg = " branch" if getattr(it, "branch", False) else ""
            out.append(f"{NAMES[level]} {{#{it.id}{flg}}} {it.text}" if it.id else f"{NAMES[level]} {it.text}")
            items(it.children, level + 1)

    for p in art.paras:
        flags = (" counted" if p.counted else "") + (" branch" if getattr(p, "branch", False) else "")
        out.append(f"項 {{#{p.id}{flags}}} {p.text}" if p.id else f"項 {p.text}")
        items(p.items, 1)
    return "\n".join(out)


def text_to_paras(text, art_id, used_ids):
    """編集用テキストを項・号に戻す。IDの無い行には art_id を元に新しいIDを付ける。"""
    used = set(used_ids)
    paras, stack = [], []
    counters = [0, 0, 0, 0]
    # 行頭の語（項・号・細・目）がまったく無いときは、1行を1つの項として扱う（そのまま文章を入れた場合）
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines and not any(LINE.match(ln) for ln in lines):
        text = "\n".join("項 " + ln.strip() for ln in lines)

    def new_id(level):
        counters[level] += 1
        while True:
            base = art_id + "".join(
                f"-{('p', 'i', 's', 't')[i]}{counters[i]}" for i in range(level + 1))
            if base not in used:
                used.add(base)
                return base
            counters[level] += 1

    errors = []
    for n, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        m = LINE.match(raw)
        if not m:
            if stack:
                stack[-1].text += "\n" + raw.strip()
            else:
                errors.append(f"{n}行目: 行の先頭に「項」と書いてください（番号ではなく、文字の「項」です）。例: 項 区分所有者は、…")
            continue
        level = LEVELS[m.group(1)]
        nid, flags, body = m.group(2) or "", (m.group(3) or "").split(), m.group(4)
        if level == 0:
            counters[1] = counters[2] = counters[3] = 0
            counters[0] = max(counters[0], len(paras))
            node = Para(nid or new_id(0), body, [], 0, "counted" in flags, "branch" in flags)
            paras.append(node)
            stack = [node]
        else:
            if len(stack) < level:
                errors.append(f"{n}行目: 「{m.group(1)}」の上に、1つ上の階層の行が必要です")
                continue
            parent = stack[level - 1]
            it = Item(nid or new_id(level), body, level, [], 0, "branch" in flags)
            (parent.items if isinstance(parent, Para) else parent.children).append(it)
            stack = stack[:level] + [it]
        if nid:
            used.add(nid)
    if not paras and not errors:
        errors.append("本文がありません（先頭に「項」の行が必要です）")
    return paras, errors


def all_ids(doc):
    ids = set()

    def items(lst):
        for it in lst:
            ids.add(it.id)
            items(it.children)

    for el in doc.elements:
        ids.add(el.id)
        for p in el.paras:
            ids.add(p.id)
            items(p.items)
    ids.discard("")
    return ids


def gen_article_id(doc, base="art-new"):
    ids = all_ids(doc)
    n = 1
    while f"{base}-{n}" in ids:
        n += 1
    return f"{base}-{n}"


def edit_article(doc, art_id, title, text):
    """条の見出しと本文を差し替える。エラーの一覧を返す（空なら成功）。"""
    art = find_article(doc, art_id)
    others = all_ids(doc) - {art.id}
    paras, errors = text_to_paras(text, art.id, others)
    if errors:
        return errors
    art.title = title.strip()
    art.paras = paras
    return []


def add_article(doc, after_id, title, text, branch=False, new_id=None):
    """after_id の条の直後に新しい条を入れる。after_id が空なら先頭。"""
    new_id = new_id or gen_article_id(doc)
    if new_id in all_ids(doc):
        return ["そのIDはすでに使われています: " + new_id], None
    paras, errors = text_to_paras(text, new_id, all_ids(doc))
    if errors:
        return errors, None
    art = Article(new_id, title.strip(), {"branch"} if branch else set(), paras, 0, False, branch)
    pos = 0
    if after_id:
        pos = next(i for i, el in enumerate(doc.elements) if el.id == after_id) + 1
    doc.elements.insert(pos, art)
    return [], art


def delete_article(doc, art_id):
    """条を「削除」にする（番号の枠とIDは残す）。"""
    art = find_article(doc, art_id)
    art.deleted = True
    art.flags.add("deleted")


def save(doc):
    Path(doc.path).write_text(dump_doc(doc), encoding="utf-8", newline="\n")

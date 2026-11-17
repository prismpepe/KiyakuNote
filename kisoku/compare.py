"""新旧対照表の生成。条のIDで新旧を対応づけ、番号は各版で計算した値を出す。

分類:
  新設 / 削除 / 改正（本文・見出しが変わった）
  参照の自動更新（本文は同じで、参照している条番号が繰り下がりなどで変わっただけ）
  条番号のみ変更（本文は同じで、条の番号だけ変わった）
"""
import difflib
from .core import Heading
from .render import article_text, article_source, render_appendices

KINDS = ("新設", "削除", "改正", "参照の自動更新", "条番号のみ変更")


def merge_order(old_arts, new_arts):
    """新しい版の順を基準に、削除された条を、元の位置の直後に差し込んだ並びを返す。"""
    new_ids = [a.id for a in new_arts]
    result = list(new_arts)
    pos = {a.id: i for i, a in enumerate(result)}
    prev = None
    for a in old_arts:
        if a.id in pos:
            prev = a.id
            continue
        i = pos[prev] + 1 if prev in pos else 0
        result.insert(i, a)
        pos = {x.id: k for k, x in enumerate(result)}
        prev = a.id
    return result


def inline_diff(old, new):
    """文字単位の差分を、旧側は ~~削除~~、新側は **追加** で示す。"""
    # 全角・半角の数字の違いは、変更として示さない（照合は半角にそろえ、表示は元の文字のまま）
    digits = str.maketrans("０１２３４５６７８９", "0123456789")
    sm = difflib.SequenceMatcher(None, old.translate(digits), new.translate(digits), autojunk=False)
    o, n = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            o.append(old[i1:i2])
            n.append(new[j1:j2])
            continue
        if i2 > i1:
            o.append("~~" + old[i1:i2].replace("\n", "~~\n~~") + "~~")
        if j2 > j1:
            n.append("**" + new[j1:j2].replace("\n", "**\n**") + "**")
    fix = lambda s: s.replace("~~~~", "").replace("****", "")
    return fix("".join(o)), fix("".join(n))


def same_text(x, y):
    """全角・半角の違いと空白を無視した、出力文字の一致。"""
    import re
    import unicodedata
    f = lambda t: re.sub(r"\s+", "", unicodedata.normalize("NFKC", t))
    return f(x) == f(y)


def classify(reg_old, reg_new, doc_id, a_old, a_new):
    """条の変更の種類。変更なしは None。

    出力される文字（番号・参照を展開したあと）が同じなら、ソースの書き方だけが違う（番号の直書きをIDの参照に
    直した等）ので、変更として載せない。
    """
    if a_old is None:
        return "新設"
    if a_new is None:
        return "削除"
    if a_new.deleted and not a_old.deleted:
        return "削除"
    t_old = article_text(reg_old, reg_old.docs[doc_id], a_old)
    t_new = article_text(reg_new, reg_new.docs[doc_id], a_new)
    if same_text(t_old, t_new):
        return "条番号のみ変更" if a_old.label != a_new.label else None
    if article_source(a_old) != article_source(a_new):
        return "改正"
    # 本文のソースは同じで、出力が違う: 見出しの番号だけか、本文中の参照が変わったか
    if same_text("".join(t_old.split("\n", 1)[1:]), "".join(t_new.split("\n", 1)[1:])):
        return "条番号のみ変更"
    return "参照の自動更新"


def compare_doc(reg_old, reg_new, doc_id):
    """1文書の変更行 [(種類, 旧テキスト, 新テキスト)] を返す。"""
    d_old, d_new = reg_old.docs.get(doc_id), reg_new.docs.get(doc_id)
    if d_old is None and d_new is None:
        return []
    olds = {a.id: a for a in (d_old.articles if d_old else [])}
    news = {a.id: a for a in (d_new.articles if d_new else [])}
    rows = []
    for a in merge_order(d_old.articles if d_old else [], d_new.articles if d_new else []):
        ao, an = olds.get(a.id), news.get(a.id)
        kind = classify(reg_old, reg_new, doc_id, ao, an)
        if kind is None:
            continue
        to = article_text(reg_old, d_old, ao) if ao else "（新設）"
        tn = article_text(reg_new, d_new, an) if an else "（削除）"
        if kind in ("改正", "参照の自動更新") and ao and an:
            to, tn = inline_diff(to, tn)
        rows.append((kind, to, tn))
    return rows


def appendix_changes(reg_old, reg_new):
    """別表・別紙・別図の本体が変わったもの。表の中身の差分は出さず、変更の有無だけ示す。"""
    out = []
    ids = list(reg_new.docs) + [i for i in reg_old.docs if i not in reg_new.docs]
    for i in ids:
        o, n = reg_old.docs.get(i), reg_new.docs.get(i)
        d = n or o
        if d.kind not in ("別表", "別紙", "別図"):
            continue
        if o is None:
            out.append((i, d.title, "新設"))
        elif n is None:
            out.append((i, d.title, "削除"))
        elif o.raw_body != n.raw_body or o.meta.get("deleted") != n.meta.get("deleted"):
            out.append((i, d.title, "改正"))
    return out


def cell(s):
    return s.replace("|", "\\|").replace("\n", "<br>")


def render_table(reg_old, reg_new, label_old, label_new, docs=None, only_changed=True):
    ids = docs or [i for i, d in reg_new.docs.items() if d.kind not in ("別表", "別紙", "別図")]
    ids += [i for i in reg_old.docs if i not in ids and reg_old.docs[i].kind not in ("別表", "別紙", "別図")]
    out = [f"# 新旧対照表", "", f"- 改正前: {label_old}", f"- 改正後: {label_new}", ""]
    total = {k: 0 for k in KINDS}
    body = []
    for did in ids:
        rows = compare_doc(reg_old, reg_new, did)
        if not rows:
            continue
        d = reg_new.docs.get(did) or reg_old.docs[did]
        body += [f"## {d.title}", "", "| 区分 | 改正前 | 改正後 |", "|------|--------|--------|"]
        for kind, to, tn in rows:
            total[kind] += 1
            body.append(f"| {kind} | {cell(to)} | {cell(tn)} |")
        body.append("")
    ap = appendix_changes(reg_old, reg_new)
    if ap:
        body += ["## 別表・別紙・別図", "", "| 文書 | 区分 |", "|------|------|"]
        body += [f"| {t}（{i}） | {k} |" for i, t, k in ap]
        body.append("")
    summary = "、".join(f"{k} {v}件" for k, v in total.items() if v) or "変更なし"
    out += [f"変更: {summary}" + (f"、別表・別紙 {len(ap)}件" if ap else ""), ""]
    return "\n".join(out + body) + "\n"


def bare_reference_notes(reg_new):
    """IDに変換されていない条番号・相対参照（番号が変わると誤りになる）の一覧。改正前に人が確認する。"""
    from .lint import lint
    notes = []
    for sev, code, msg, doc, line in lint(reg_new):
        if code in ("W-BARE-NUM", "W-BARE-REL"):
            d = reg_new.docs[doc]
            notes.append(f"{d.title} {line}行目: {msg}")
    return notes


def render_bare_notes(notes, limit=80):
    if not notes:
        return ""
    out = ["## 要確認: IDに変換されていない参照", "",
           f"次の {len(notes)} 件は本文に番号を直書きしたままで、条番号が変わっても自動では更新されない。改正で番号が動く場合は、参照先が合っているか人が確認する。", ""]
    out += [f"- {n}" for n in notes[:limit]]
    if len(notes) > limit:
        out.append(f"- ほか {len(notes) - limit} 件")
    return "\n".join(out) + "\n"

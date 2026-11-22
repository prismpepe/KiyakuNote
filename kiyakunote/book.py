"""冊子（Word出力で「すべて」を選んだときの、一冊の管理規約）の構成。印刷専用のデータで、条文には影響しない。

構成は src/book.txt に書く（無ければ、文書から既定の構成を作る）。1行が1項目で、# で始まる行は注釈。

    表紙: ライオンズステーションプラザセンター南管理規約     ← 表紙の行（1行目が大きな題名、以降が副題）
    目次                                                       ← 目次（Wordで開いたとき、ページ番号つきに更新できる）
    中表紙: 管理規約                                           ← 区切りの扉のページ
    文書: kiyaku                                               ← 文書（規約・細則）の本文
    別表等: kiyaku                                             ← その文書の別表・別紙・別図
    改訂履歴                                                   ← 巻末の改訂履歴
    署名                                                       ← 理事長の署名（奥書）
"""
from pathlib import Path

from .core import APPENDIX_KINDS
from .search import doc_order

KEYS = ("表紙", "中表紙", "文書", "別表等")             # 「キー: 値」の形の項目
PLAIN = ("目次", "改訂履歴", "署名")                    # 値のない項目
FILE = "book.txt"


class BookError(Exception):
    pass


def parse_book(text):
    """book.txt の文字を [(項目, 値)] にする。読めない行は BookError。"""
    out = []
    for n, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        ln = raw.strip()
        if not ln or ln.startswith("#"):
            continue
        key, sep, val = ln.partition(":")
        if not sep:
            key, sep, val = ln.partition("：")
        key, val = key.strip(), val.strip()
        if key in PLAIN and not val:
            out.append((key, ""))
        elif key in KEYS and (val or key == "表紙"):
            out.append((key, val))
        else:
            raise BookError(f"{n}行目を読めません: {raw.strip()}（使える項目: {'、'.join(KEYS + PLAIN)}）")
    return out


def load_book(src_dir):
    """src_dir/book.txt の項目。ファイルが無ければ None。"""
    p = Path(src_dir) / FILE
    if not p.exists():
        return None
    return parse_book(p.read_text(encoding="utf-8-sig"))


def default_book_text(reg, effective=""):
    """文書から作る既定の構成（book.txt の文字）。規約 → 別表・別紙・別図 → 使用細則 → 細則 → 改訂履歴 → 署名。"""
    docs = sorted((d for d in reg.docs.values() if d.kind not in APPENDIX_KINDS), key=doc_order)
    main = [d for d in docs if d.kind == "規約"]
    lines = ["# 冊子（Word出力の「すべて」）の構成。1行が1項目。# で始まる行は注釈。順番を入れ替えると出力の順が変わる。", ""]
    lines.append(f"表紙: {main[0].title if main else '管理規約'}")
    if effective:
        lines.append(f"表紙: {effective}施行")
    lines += ["", "目次", ""]
    for d in main:
        lines += ["中表紙: 管理規約", f"文書: {d.id}"]
        if d.meta.get("appendices"):
            lines += ["中表紙: 別表・別紙・別図", f"別表等: {d.id}"]
    for kind in ("使用細則", "細則"):
        group = [d for d in docs if d.kind == kind]
        if not group:
            continue
        lines += ["", f"中表紙: {kind}"]
        for d in group:
            lines.append(f"文書: {d.id}")
            if d.meta.get("appendices"):
                lines.append(f"別表等: {d.id}")
    others = [d for d in docs if d.kind not in ("規約", "使用細則", "細則")]
    for d in others:
        lines += ["", f"文書: {d.id}"] + ([f"別表等: {d.id}"] if d.meta.get("appendices") else [])
    lines += ["", "改訂履歴", "署名", ""]
    return "\n".join(lines)


def plan_for(reg, src_dir, effective=""):
    """冊子の構成。book.txt があればそれ、無ければ既定。"""
    return load_book(src_dir) or parse_book(default_book_text(reg, effective))


def check_plan(reg, plan):
    """(エラー, 注意) の文のリスト。エラー: 存在しない文書。注意: 冊子に入っていない文書・同じ文書の重複。"""
    errors, notes, used = [], [], set()
    for key, val in plan:
        if key in ("文書", "別表等"):
            d = reg.docs.get(val)
            if d is None:
                errors.append(f"{key}: {val} という文書がありません")
            elif d.kind in APPENDIX_KINDS:
                errors.append(f"{key}: {val} は別表・別紙・別図です（親の文書を書いてください）")
            elif key == "文書":
                if val in used:
                    notes.append(f"文書 {val}（{d.title}）が2回入っています")
                used.add(val)
    for d in sorted(reg.docs.values(), key=doc_order):
        if d.kind not in APPENDIX_KINDS and d.id not in used:
            notes.append(f"冊子に入っていない文書: {d.title}（{d.id}）")
    if not any(k == "文書" for k, _ in plan):
        errors.append("文書が1つもありません")
    return errors, notes

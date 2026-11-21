"""使い方:
  python -m kiyakunote lint <入力フォルダ>
  python -m kiyakunote build <入力フォルダ> -o <出力フォルダ>
  python -m kiyakunote compare <改正前> <改正後> [-o 出力ファイル]
      版の指定: WORKTREE（作業中のsrc/）、@2022-04-01（その日に有効な版）、gitの参照（タグ・コミット）
  python -m kiyakunote revisions       版の一覧（src/revisions.yaml）
"""
import argparse
import sys
from pathlib import Path
from .core import Registry, load_dir, APPENDIX_KINDS
from .lint import lint
from .render import render_doc


def cmd_check(a, build):
    reg = Registry(load_dir(a.src))
    found = lint(reg)
    for sev, code, msg, doc, line in found:
        print(f"{sev} {code} {doc}:{line} {msg}")
    errors = sum(1 for f in found if f[0] == "E")
    print(f"エラー {errors} 件、警告 {len(found) - errors} 件")
    if not build:
        return 1 if errors else 0
    if errors:
        print("エラーがあるため出力しない")
        return 1
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for d in reg.docs.values():
        if d.kind in APPENDIX_KINDS:
            continue
        (out / f"{d.id}.md").write_text(render_doc(reg, d), encoding="utf-8", newline="\n")
        print("出力:", out / f"{d.id}.md")
    return 0


def cmd_docx(a):
    from .docx_out import build_docx
    reg = Registry(load_dir(a.src))
    errors = [f for f in lint(reg) if f[0] == "E"]
    if errors:
        for sev, code, msg, doc, line in errors:
            print(f"{sev} {code} {doc}:{line} {msg}")
        print("エラーがあるため出力しない")
        return 1
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for d in reg.docs.values():
        if d.kind in APPENDIX_KINDS or (a.doc and d.id != a.doc):
            continue
        build_docx(reg, d, out / f"{d.id}.docx", src_dir=a.src)
        print("出力:", out / f"{d.id}.docx")
    return 0


def cmd_compare(a):
    from .compare import render_table
    from .versions import resolve, load_version, load_revisions
    revs = load_revisions()
    ro, rn = resolve(a.old, revs), resolve(a.new, revs)
    if a.out and a.out.lower().endswith(".docx"):
        from .docx_out import build_compare_docx
        from .compare import bare_reference_notes
        build_compare_docx(load_version(ro), load_version(rn), f"{a.old}（{ro}）", f"{a.new}（{rn}）", a.out,
                           notes=bare_reference_notes(load_version(rn)))
        print("出力:", a.out)
        return 0
    from .compare import bare_reference_notes, render_bare_notes
    reg_new = load_version(rn)
    notes = bare_reference_notes(reg_new)
    text = render_table(load_version(ro), reg_new, f"{a.old}（{ro}）", f"{a.new}（{rn}）") + render_bare_notes(notes)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8", newline="\n")
        print("出力:", a.out)
    else:
        sys.stdout.write(text)
    return 0


DB = Path("out") / "search.db"


def cmd_index(a):
    from .search import build_index
    from .versions import resolve, load_version
    ref = resolve(a.at) if a.at else "WORKTREE"
    n = build_index(load_version(ref), a.db)
    Path(str(a.db) + ".ref").write_text(ref, encoding="utf-8")     # どの版から作った索引かを覚えておく
    print(f"索引を作った: {a.db}（{n}行、版: {ref}）")
    return 0


def ensure_db(a):
    from .versions import resolve
    ref = resolve(a.at) if getattr(a, "at", None) else "WORKTREE"
    side = Path(str(a.db) + ".ref")
    made = side.read_text(encoding="utf-8") if side.exists() else None
    # 別の版から作った索引が残っているときは、作り直す（黙って別の版を検索しない）
    if a.rebuild or not Path(a.db).exists() or made != ref:
        cmd_index(a)


def cmd_search(a):
    from .search import search, snippet
    ensure_db(a)
    try:
        rows = search(a.db, " ".join(a.query), doc=a.doc, kind=a.kind, level=a.level, limit=a.limit, regex=a.regex)
    except ValueError as e:
        print(f"エラー: {e}")
        return 2
    for title, doc, label, art_title, text, level, nid in rows:
        head = f"{title} {label}" + (f"（{art_title}）" if art_title and level == "article" else "")
        print(head)
        print("    " + snippet(text or art_title, " ".join(a.query), regex=a.regex))
    print(f"{len(rows)}件" + ("（上限）" if len(rows) >= a.limit else ""))
    return 0


def cmd_refs(a):
    from .search import refs_of
    ensure_db(a)
    out, inc = refs_of(a.db, a.ident)
    print("この条が参照している先:")
    for fl, td, tl in out:
        print(f"  {fl} → {tl}")
    print("この条を参照している元:")
    for fd, fl, tl in inc:
        print(f"  {fd} {fl} → {tl}")
    return 0


def cmd_revisions(a):
    from .versions import load_revisions
    for r in load_revisions():
        ref = r.get("ref") or "（本文なし）"
        print(f"{r['resolution']} 決議 / {r['effective'] or '施行日なし'} 施行  {ref}  {len(r['changes'])}件")
    return 0


def main(argv=None):
    # 日本語を出せない文字コードのコンソール（英語環境の Windows、リダイレクトなど）でも落ちないようにする
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                       # noqa: BLE001
            pass
    from . import __version__
    ap = argparse.ArgumentParser(prog="kiyakunote", description="規約ノート（KiyakuNote） マンション管理規約 編集・改正履歴管理システム")
    ap.add_argument("--version", action="version", version=f"規約ノート KiyakuNote {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("lint", "build"):
        p = sub.add_parser(name)
        p.add_argument("src")
        p.add_argument("-o", "--out", default="out")
    p = sub.add_parser("docx")
    p.add_argument("src")
    p.add_argument("-o", "--out", default="out")
    p.add_argument("--doc", help="この文書IDだけ出力する（例 kiyaku）")
    p = sub.add_parser("compare")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("-o", "--out")
    sub.add_parser("revisions")
    sub.add_parser("gui")
    for name in ("index", "search", "refs"):
        p = sub.add_parser(name)
        p.add_argument("--db", default=str(DB))
        p.add_argument("--at", help="版の指定（@2022-04-01 など）。省略は作業中のsrc/")
        p.add_argument("--rebuild", action="store_true", help="索引を作り直す")
        if name == "search":
            p.add_argument("query", nargs="+")
            p.add_argument("--doc")
            p.add_argument("--kind", help="規約 / 使用細則 / 細則 / 別表 / 別紙 / 別図")
            p.add_argument("--level", choices=["article", "para", "item", "appendix"])
            p.add_argument("--limit", type=int, default=30)
            p.add_argument("-E", "--regex", action="store_true", help="検索語を正規表現として使う（空白で区切らず、全体で1つの式）")
        if name == "refs":
            p.add_argument("ident", help="条・項・号のID（例 art-023、kiyaku#art-023）")
    a = ap.parse_args(argv)
    if a.cmd == "index":
        return cmd_index(a)
    if a.cmd == "search":
        return cmd_search(a)
    if a.cmd == "refs":
        return cmd_refs(a)
    if a.cmd == "gui":
        from .gui import main as gui_main
        gui_main()
        return 0
    if a.cmd == "docx":
        return cmd_docx(a)
    if a.cmd == "compare":
        return cmd_compare(a)
    if a.cmd == "revisions":
        return cmd_revisions(a)
    return cmd_check(a, a.cmd == "build")


if __name__ == "__main__":
    sys.exit(main())

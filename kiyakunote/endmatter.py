"""規約の巻末の項目: 改訂履歴（表）と、理事長の署名（奥書）。

- 改訂履歴は src/revisions.yaml から作る。過去の版を表示しているときは、その版の施行日までの分に限る。
- 奥書は src/okugaki.txt（普通の文章。空行で段落を分ける）。無ければ「署名なし」として出さない。
  過去の版では、そのタグにある okugaki.txt を使う。
"""
from pathlib import Path

HISTORY_TITLE = "改訂履歴"
SIGN_TITLE = "理事長の署名（奥書）"
HEAD = ("総会日", "施行日", "改定内容")


def history_for(revs, ref="WORKTREE"):
    """表示する版の分の改訂履歴。ref が WORKTREE か、一覧に無いタグなら全部。"""
    if ref and ref != "WORKTREE":
        me = next((r for r in revs if r.get("ref") == ref), None)
        if me and me.get("effective"):
            return [r for r in revs if (r.get("effective") or "") <= me["effective"]]
    return list(revs)


def history_rows(revs):
    """改訂履歴を、行×3列の文字（1行目は見出し）にする。"""
    rows = [list(HEAD)]
    for r in revs:
        parts = [n for n in r.get("notes", [])] + ["・" + c if not c.startswith("・") else c for c in r.get("changes", [])]
        rows.append([r.get("resolution", ""), r.get("effective", ""), "\n".join(parts)])
    return rows


def history_cells(revs):
    """画面の表（gui_table.table_frame）に渡すセルの並び (行, 列, 行結合, 列結合, 文字, 見出しか)。"""
    return [(r, c, 1, 1, t, r == 0) for r, row in enumerate(history_rows(revs)) for c, t in enumerate(row)]


def load_okugaki(src_dir):
    """奥書の段落のリスト。ファイルが無ければ空。"""
    p = Path(src_dir) / "okugaki.txt"
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    return [x.strip("\n") for x in text.split("\n\n") if x.strip()]

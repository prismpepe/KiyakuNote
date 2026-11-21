"""GUI のスクリーンショットを docs/images/ に作る（Windows、Pillow が必要）。

使い方（プロジェクトのフォルダで）:  python tools/take_screenshots.py
画面に実際に出して撮るので、実行中は他のウィンドウを操作しないでください。
"""
import ctypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "images"

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)       # 座標と画面の画素を一致させる
except Exception:                                        # noqa: BLE001
    pass

from PIL import ImageGrab  # noqa: E402

from kiyakunote.gui import App  # noqa: E402

from tkinter import messagebox  # noqa: E402

# 誤りを見せる撮影のとき、読み込みのエラー画面が出て止まらないようにする
messagebox.showerror = lambda *a, **k: None
messagebox.showinfo = lambda *a, **k: None
messagebox.showwarning = lambda *a, **k: None


def grab(win, name):
    win.update_idletasks()
    win.update()
    win.after(250)
    win.update()
    x, y = win.winfo_rootx(), win.winfo_rooty()
    w, h = win.winfo_width(), win.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / name)
    print("保存:", OUT / name)


def settle(app, ms=400):
    end = app.tk.call("clock", "milliseconds") + ms
    while app.tk.call("clock", "milliseconds") < end:
        app.update()


def main():
    app = App()
    app.geometry("1280x820+40+30")
    app.attributes("-topmost", True)
    app.lift()
    settle(app, 600)

    # 1. 条文
    app.goto("kiyaku", "art-repair")
    settle(app)
    grab(app, "01-read.png")

    # 2. 検索
    app.nb.select(app.tab_search)
    app.s_q.delete(0, "end")
    app.s_q.insert(0, "駐車場 使用料")
    app.do_search()
    settle(app)
    grab(app, "02-search.png")

    # 2b. 正規表現の検索（一致した語は黄色）
    app.s_q.delete(0, "end")
    app.s_q.insert(0, "第[0-9]+条")
    app.s_re.set(True)
    app.do_search()
    settle(app)
    grab(app, "02b-regex.png")
    app.s_re.set(False)

    # 3. 整合性チェック
    # 見せるために、一時的に誤りを入れる（撮り終えたら元に戻す）
    kiyaku = ROOT / "src" / "kiyaku.md"
    original = kiyaku.read_bytes()
    try:
        t = original.decode("utf-8")
        t = t.replace("{ref:art-repair-p1|rel}の申請", "前項の申請")                # 相対参照の直書き（警告）
        t = t.replace("{ref:art-def-p1-i2}は、", "第3条は、")                         # 条番号の直書き（警告）
        t = t.replace("{ref:tbl-1}に掲げる", "{ref:tbl-99}に掲げる")                  # 存在しない参照（エラー）
        t = t.replace("{ref:art-sinking-p2}の取崩し", "{ref:art-duty}の取崩し")        # 削除済みの条への参照（エラー）
        kiyaku.write_bytes(t.encode("utf-8"))
        app.load_version()
        app.nb.select(app.tab_lint)
        app.do_lint()
        settle(app)
        grab(app, "03-lint.png")
    finally:
        kiyaku.write_bytes(original)
        app.load_version()

    # 4. 新旧対照表（2018年版 → 2022年版）
    app.nb.select(app.tab_cmp)
    labels = list(app.versions)
    old = next(v for v in labels if "v2018" in v)
    new = next(v for v in labels if "v2022" in v)
    app.c_old.set(old)
    app.c_new.set(new)
    app.do_compare()
    settle(app)
    kids = app.c_tree.get_children()
    pick = next((k for k in kids if app.cmp_rows[int(k)][0] == "改正"), kids[0])
    app.c_tree.selection_set(pick)
    app.c_tree.see(pick)
    app.on_cmp_select()
    settle(app)
    grab(app, "04-compare.png")

    # 5. Word 出力
    app.nb.select(app.tab_out)
    settle(app)
    grab(app, "05-docx.png")

    # 6. 版の一覧
    app.nb.select(app.tab_rev)
    first = app.r_tree.get_children()[-1]
    app.r_tree.selection_set(first)
    app.on_rev()
    settle(app)
    grab(app, "06-revisions.png")

    # 6b. 変更履歴（git のコマンドを使わずに履歴・差分を見られる）
    app.nb.select(app.tab_hist)
    app.fill_hist()
    kids = app.h_tree.get_children()
    if kids:
        app.h_tree.selection_set(kids[0])
        app.hist_show_selected()
    settle(app, 600)
    grab(app, "09-history.png")

    # 6c. 別表・別紙の表（罫線つき）
    app.nb.select(app.tab_read)
    first_tbl = next((i for i, d in app.reg.docs.items() if d.kind == "別表"), None)
    if first_tbl:
        app.tree.selection_set(first_tbl)
        app.tree.see(first_tbl)
        app.on_tree()
        settle(app, 600)
        grab(app, "08-table.png")

    # 6d. 表示設定
    from kiyakunote.gui_settings import SettingsDialog
    dlg = SettingsDialog(app)
    settle(dlg, 800)
    grab(dlg, "10-settings.png")
    dlg.destroy()

    # 7. 条の編集画面
    app.nb.select(app.tab_read)
    app.goto("kiyaku", "art-repair")
    settle(app)
    before = set(app.winfo_children())
    app.edit_selected()
    settle(app, 600)
    dlg = next((w for w in app.winfo_children() if w not in before and w.winfo_class() == "Toplevel"), None)
    if dlg is not None:
        dlg.geometry("+120+80")
        dlg.attributes("-topmost", True)
        dlg.lift()
        settle(dlg, 500)
        grab(dlg, "07-edit.png")
        dlg.destroy()
    app.destroy()


if __name__ == "__main__":
    main()

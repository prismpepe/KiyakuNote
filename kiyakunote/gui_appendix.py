"""別表・別紙・別図を画面で編集するダイアログ（表のセル、新設）。処理本体は appendix_edit・tables・xlsx_io。"""
import os
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import appendix_edit as ae
from . import tables as T
from . import xlsx_io
from .gui_style import place_dialog

NL = "↵"          # セルの中の改行を、入力欄では ↵ で表す


class TableEditDialog(tk.Toplevel):
    """表（結合セルも可）のセルの文字を書き換え、行・列を足したり消したりする。Excel との受け渡しもできる。"""

    def __init__(self, app, doc):
        super().__init__(app)
        self.app, self.doc = app, doc
        self.title(f"表を編集 — {doc.title}")
        self.geometry("1040x660")
        self.transient(app)
        place_dialog(self, app)
        self.tables = self.get_tables()
        self.xlsx = None                                   # 「Excelで編集」で作った一時ファイル
        self.cells, self.entries, self.cur = [], [], 0
        self.history = []                                  # 行・列・結合の操作の前の状態（「操作を元に戻す」用）
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(10, 4))
        self.which = ttk.Combobox(top, state="readonly", width=24, values=[f"表{i + 1}" for i in range(len(self.tables))])
        self.which.current(0)
        self.which.bind("<<ComboboxSelected>>", lambda e: self.load())
        if len(self.tables) > 1:
            ttk.Label(top, text="編集する表:").pack(side="left")
            self.which.pack(side="left", padx=6)
        self.status = ttk.Label(top, text="", style="Hint.TLabel")
        self.status.pack(side="left", padx=10)
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=2)
        for text, cmd in (("行を上に追加", lambda: self.add_row(False)), ("行を下に追加", lambda: self.add_row(True)), ("行を削除", self.del_row),
                          ("列を左に追加", lambda: self.add_col(False)), ("列を右に追加", lambda: self.add_col(True)), ("列を削除", self.del_col)):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=3)
        mb = ttk.Frame(self)
        mb.pack(fill="x", padx=10, pady=2)
        ttk.Label(mb, text="セルの結合:", style="Hint.TLabel").pack(side="left", padx=(0, 6))
        for text, cmd in (("右のセルと結合", lambda: self.merge(T.merge_right)), ("下のセルと結合", lambda: self.merge(T.merge_down)),
                          ("結合を解除", lambda: self.merge(T.unmerge))):
            ttk.Button(mb, text=text, command=cmd).pack(side="left", padx=3)
        ttk.Button(mb, text="操作を元に戻す", command=self.undo_op).pack(side="left", padx=(18, 3))
        xb = ttk.Frame(self)
        xb.pack(fill="x", padx=10, pady=2)
        ttk.Label(xb, text="Excel:", style="Hint.TLabel").pack(side="left", padx=(0, 6))
        for text, cmd in (("Excelで編集…", self.excel_edit), ("Excelの変更を取り込む", self.excel_back),
                          ("Excelファイルに書き出し…", self.excel_save), ("Excelファイルから取り込み…", self.excel_open)):
            ttk.Button(xb, text=text, command=cmd).pack(side="left", padx=3)
        ttk.Label(self, text=f"枠をクリックして書き換えます（青い枠は見出し）。セルの中で改行したいところには {NL} を入れます。結合セルは大きな枠になります。\n"
                             "行・列の追加と削除は、いま選んでいる枠を基準にします（結合セルのある行・列では、結合していない枠を選ぶと分かりやすい）。",
                  style="Hint.TLabel").pack(anchor="w", padx=10)
        box = ttk.Frame(self)
        box.pack(fill="both", expand=True, padx=10, pady=6)
        self.canvas = tk.Canvas(box, background="#ffffff", highlightthickness=1, highlightbackground="#8a8a8a")
        vs = ttk.Scrollbar(box, command=self.canvas.yview)
        hs = ttk.Scrollbar(box, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        hs.pack(side="bottom", fill="x")
        vs.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<MouseWheel>", self.wheel)
        bt = ttk.Frame(self)
        bt.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bt, text="保存", command=self.save, style="Accent.TButton").pack(side="right")
        ttk.Button(bt, text="キャンセル", command=self.close).pack(side="right", padx=6)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.load()

    def entry_width(self, c, cs):
        return max(8, min(30, 10 * cs + 6))

    def get_tables(self):
        return T.list_tables(self.doc.raw_body)

    def wheel(self, ev):
        self.canvas.yview_scroll(-1 if ev.delta > 0 else 1, "units")

    def index(self):
        return self.which.current() if self.which.current() >= 0 else 0

    def load(self):
        self.history = []
        self.set_cells(T.fill_holes(self.tables[self.index()]["cells"]))

    # ---- 格子の表示 ----
    def set_cells(self, cells):
        self.cells = sorted(cells, key=lambda x: (x[0], x[1]))
        self.draw()

    def draw(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.entries = []
        for i, (r, c, rs, cs, text, th) in enumerate(self.cells):
            e = tk.Entry(self.inner, width=self.entry_width(c, cs), font=self.app.styler.f_input, relief="solid", borderwidth=1,
                         background="#dbe5f1" if th else "#ffffff")
            e.insert(0, text.replace("\n", NL))
            e.grid(row=r, column=c, rowspan=rs, columnspan=cs, sticky="nsew")
            e.bind("<FocusIn>", lambda ev, k=i: self.focus_cell(k))
            e.bind("<MouseWheel>", self.wheel)
            self.entries.append(e)
        self.cur = min(self.cur, len(self.cells) - 1)
        self.show_status()

    def focus_cell(self, k):
        self.cur = k
        self.show_status()

    def show_status(self):
        if not self.cells:
            return
        r, c, rs, cs, _, _ = self.cells[self.cur]
        nr, nc = T.table_size(self.cells)
        span = f"（結合 {rs}行×{cs}列）" if rs > 1 or cs > 1 else ""
        self.status.config(text=f"表は {nr}行×{nc}列　選択中: {r + 1}行目・{c + 1}列目{span}")

    def sync(self):
        """入力欄の文字を、セルの一覧に戻す。"""
        self.cells = [(r, c, rs, cs, e.get().replace(NL, "\n"), th) for (r, c, rs, cs, _, th), e in zip(self.cells, self.entries)]

    # ---- 行・列の操作 ----
    def op(self, fn, *a):
        if not self.cells:
            return
        self.sync()
        try:
            new = fn(self.cells, *a)
        except ValueError as e:
            messagebox.showinfo("できません", str(e), parent=self)
            return
        self.history.append(self.cells)
        self.set_cells(new)

    def undo_op(self):
        """直前の行・列・結合の操作（Excel の取り込みも）を元に戻す。"""
        if not self.history:
            messagebox.showinfo("元に戻す", "元に戻せる操作がありません。", parent=self)
            return
        self.sync()
        self.set_cells(self.history.pop())

    def merge(self, fn):
        """いま選んでいる枠を、右・下の枠と結合する／結合を解除する。"""
        self.op(fn, self.cur)

    def add_row(self, below):
        r, _, rs, _, _, _ = self.cells[self.cur]
        self.op(T.insert_row, r + rs - 1 if below else r - 1)

    def del_row(self):
        self.op(T.delete_row, self.cells[self.cur][0])

    def add_col(self, right):
        _, c, _, cs, _, _ = self.cells[self.cur]
        self.op(T.insert_col, c + cs - 1 if right else c - 1)

    def del_col(self):
        self.op(T.delete_col, self.cells[self.cur][1])

    # ---- Excel ----
    def excel_edit(self):
        """表を一時の Excel ファイルに書き出して Excel で開く。Excel で保存したら「Excelの変更を取り込む」。"""
        if not self.cells:
            return
        self.sync()
        path = Path(tempfile.gettempdir()) / f"KiyakuNote-{self.doc.id}-{self.index() + 1}.xlsx"
        try:
            xlsx_io.export_cells(self.cells, path)
            os.startfile(str(path))                         # noqa: S606  （関連づけられた Excel で開く）
        except (xlsx_io.XlsxError, OSError, PermissionError) as e:
            messagebox.showerror("Excelで開けません", f"{e}\n（すでに Excel で開いている場合は、閉じてからやり直してください）", parent=self)
            return
        self.xlsx = path
        messagebox.showinfo("Excelで編集", "Excelで表を開きました。\n書き換えて「上書き保存」したら、この画面に戻って「Excelの変更を取り込む」を押してください。\n"
                                          "（結合セルは Excel の結合セルとして扱われます。取り込んだあとも、ここで「保存」するまでは条文のファイルは変わりません）", parent=self)

    def excel_back(self):
        if self.xlsx is None or not Path(self.xlsx).exists():
            self.excel_open()
            return
        self.import_from(self.xlsx)

    def excel_open(self):
        p = filedialog.askopenfilename(parent=self, title="Excelファイルを選ぶ", filetypes=[("Excel ブック", "*.xlsx *.xlsm"), ("すべて", "*.*")])
        if p:
            self.import_from(p)

    def import_from(self, path):
        try:
            cells = xlsx_io.import_cells(path)
        except xlsx_io.XlsxError as e:
            messagebox.showerror("取り込めません", str(e), parent=self)
            return
        nr, nc = T.table_size(cells)
        if not messagebox.askyesno("Excelから取り込み", f"Excel の表（{nr}行×{nc}列）で、いま画面にある表を置き換えます。よろしいですか？\n（「保存」するまで、条文のファイルは変わりません）", parent=self):
            return
        self.sync()
        self.history.append(self.cells)
        self.cur = 0
        self.set_cells(cells)

    def excel_save(self):
        if not self.cells:
            return
        self.sync()
        p = filedialog.asksaveasfilename(parent=self, title="Excelファイルに書き出す", defaultextension=".xlsx",
                                         initialfile=f"{self.doc.id}-{self.index() + 1}.xlsx", filetypes=[("Excel ブック", "*.xlsx")])
        if not p:
            return
        try:
            xlsx_io.export_cells(self.cells, p)
        except (xlsx_io.XlsxError, OSError) as e:
            messagebox.showerror("書き出せません", str(e), parent=self)
            return
        messagebox.showinfo("書き出しました", p, parent=self)

    # ---- 保存 ----
    def close(self):
        if self.xlsx is not None:
            try:
                Path(self.xlsx).unlink(missing_ok=True)
            except OSError:
                pass
        self.destroy()

    def save(self):
        if not self.cells:
            self.close()
            return
        self.sync()
        path = Path(self.doc.path)
        old = path.read_bytes()
        try:
            ae.save_table_cells(path, self.index(), self.cells)
        except (ae.AppendixError, ValueError) as e:
            messagebox.showerror("保存できません", str(e), parent=self)
            return
        self.app.undo.append((path, old))
        self.close()
        self.app.after_appendix(self.doc.id, "表を保存しました")


class HistoryEditDialog(TableEditDialog):
    """改訂履歴（src/revisions.yaml）を表として編集する。列: 総会日・施行日・版のタグ・備考・改定内容（1行に1件。↵ で区切る）。"""
    HEAD = ["総会決議日", "施行日", "版のタグ（条文を持つ版）", "備考", "改定内容（↵ で区切る）"]

    def __init__(self, app):
        from types import SimpleNamespace
        from .versions import ROOT
        self.path = Path(getattr(app.reg, "src_dir", ROOT / "src")) / "revisions.yaml"
        super().__init__(app, SimpleNamespace(title="改訂履歴", id="revisions", path=str(self.path), raw_body=""))
        self.title("改訂履歴を編集（日付は 2026-04-19 の形。版のタグは条文を持つ版だけ）")

    def entry_width(self, c, cs):
        return 70 if c == 4 else 22 if c == 3 else 16

    def get_tables(self):
        from .versions import load_revisions
        revs = load_revisions(self.path)
        rows = [list(self.HEAD)]
        for r in revs:
            rows.append([r.get("resolution", ""), r.get("effective", ""), r.get("ref", ""), "\n".join(r.get("notes", [])), "\n".join(r.get("changes", []))])
        return [{"cells": [(i, c, 1, 1, t, i == 0) for i, row in enumerate(rows) for c, t in enumerate(row)]}]

    def save(self):
        import re
        from .versions import dump_revisions
        if not self.cells:
            self.close()
            return
        self.sync()
        rows = T.cells_to_rows(self.cells)[1:]
        revs = []
        for n, row in enumerate(rows, 2):
            res, eff, ref, note, changes = (x.strip() for x in row)
            if not (res or eff or ref or note or changes):
                continue                                                       # 空の行は無視
            for label, v in (("総会決議日", res), ("施行日", eff)):
                if v and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                    messagebox.showerror("保存できません", f"{n}行目の{label}「{v}」は、2026-04-19 の形で書いてください。", parent=self)
                    return
            if not res:
                messagebox.showerror("保存できません", f"{n}行目に総会決議日がありません。", parent=self)
                return
            revs.append({"resolution": res, "effective": eff, "ref": ref, "notes": [x.strip() for x in note.split("\n") if x.strip()],
                         "changes": [x.strip().lstrip("・").strip() for x in changes.split("\n") if x.strip()]})
        old = self.path.read_bytes()
        self.path.write_text(dump_revisions(revs), encoding="utf-8", newline="\n")
        self.app.undo.append((self.path, old))
        self.close()
        self.app.after_appendix("@history", "改訂履歴を保存しました")


class SignEditDialog(tk.Toplevel):
    """理事長の署名（奥書、src/okugaki.txt）を編集する。空行で段落を分ける。"""

    def __init__(self, app):
        super().__init__(app)
        from .versions import ROOT
        self.app = app
        self.path = Path(getattr(app.reg, "src_dir", ROOT / "src")) / "okugaki.txt"
        self.title("理事長の署名（奥書）を編集")
        self.geometry("760x420")
        self.transient(app)
        place_dialog(self, app)
        ttk.Label(self, text="規約の巻末に付く文章です。空行で段落を分けます（最後の段落ほど右寄せで Word に出ます）。\n"
                             "例: 証明の文 → 空行 → 日付 → 空行 → 管理組合名・理事長名・印", style="Hint.TLabel").pack(anchor="w", padx=10, pady=(10, 4))
        self.text = app.styler.text_widget(self, "input", wrap="char", height=10)
        self.text.pack(fill="both", expand=True, padx=10, pady=4)
        if self.path.exists():
            self.text.insert("1.0", self.path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").rstrip("\n"))
        bt = ttk.Frame(self)
        bt.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bt, text="保存", command=self.save, style="Accent.TButton").pack(side="right")
        ttk.Button(bt, text="キャンセル", command=self.destroy).pack(side="right", padx=6)

    def save(self):
        body = self.text.get("1.0", "end").strip("\n")
        old = self.path.read_bytes() if self.path.exists() else None
        self.path.write_text(body + "\n" if body.strip() else "", encoding="utf-8", newline="\n")
        self.app.undo.append((self.path, old))
        self.destroy()
        self.app.after_appendix("@sign", "署名（奥書）を保存しました" if body.strip() else "署名（奥書）を空にしました")


class BookEditDialog(tk.Toplevel):
    """冊子（Word出力の「すべて」）の構成 src/book.txt を編集する。印刷専用で、条文には影響しない。"""

    def __init__(self, app):
        super().__init__(app)
        from . import book
        from .versions import ROOT
        self.app, self.book = app, book
        self.src = Path(getattr(app.reg, "src_dir", ROOT / "src"))
        self.path = self.src / book.FILE
        self.editable = app.versions[app.ver.get()] == "WORKTREE"
        self.title("冊子の構成を編集" if self.editable else "冊子の構成（過去の版は見るだけ）")
        self.geometry("900x640")
        self.transient(app)
        place_dialog(self, app)
        ttk.Label(self, text="Word出力の「（すべて）」で、一冊にまとめるときの構成です。1行が1項目で、上から順に出力されます（# で始まる行は注釈）。\n"
                             "表紙: 題名　／　目次　／　中表紙: 題名　／　文書: 文書ID　／　別表等: 文書ID（その文書の別表・別紙・別図）　／　改訂履歴　／　署名\n"
                             "行を切り取って貼り付けると、順番を入れ替えられます。文書IDは、左の一覧の文書の ID です（kiyaku、bylaw-03 など）。",
                  style="Hint.TLabel").pack(anchor="w", padx=10, pady=(10, 4))
        self.text = app.styler.text_widget(self, "input", wrap="none", height=20)
        sb = ttk.Scrollbar(self, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 10), pady=4)
        self.text.pack(fill="both", expand=True, padx=(10, 0), pady=4)
        self.known = ttk.Label(self, text="文書: " + "、".join(f"{d.id}＝{d.title}" for d in sorted(
            (d for d in app.reg.docs.values() if d.kind not in ("別表", "別紙", "別図")), key=lambda d: d.id)), style="Hint.TLabel", wraplength=860)
        bt = ttk.Frame(self)
        bt.pack(fill="x", padx=10, pady=(4, 10), side="bottom", before=self.text)
        self.known.pack(anchor="w", padx=10, pady=2, side="bottom", before=self.text)
        if self.editable:
            ttk.Button(bt, text="保存", command=self.save, style="Accent.TButton").pack(side="right")
        ttk.Button(bt, text="閉じる" if not self.editable else "キャンセル", command=self.destroy).pack(side="right", padx=6)
        if self.editable:
            ttk.Button(bt, text="既定の構成にする", command=self.reset).pack(side="left")
            ttk.Button(bt, text="確認", command=self.check).pack(side="left", padx=6)
        self.text.insert("1.0", self.current_text())
        if not self.editable:
            self.text.configure(state="disabled")

    def current_text(self):
        if self.path.exists():
            return self.path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        return self.book.default_book_text(self.app.reg, self.app.effective_label())

    def reset(self):
        if messagebox.askyesno("既定の構成にする", "いまの内容を捨てて、文書から作る既定の構成にします。よろしいですか？", parent=self):
            self.text.delete("1.0", "end")
            self.text.insert("1.0", self.book.default_book_text(self.app.reg, self.app.effective_label()))

    def check(self, quiet=False):
        """内容を確かめる。問題がなければ True。"""
        try:
            plan = self.book.parse_book(self.text.get("1.0", "end"))
        except self.book.BookError as e:
            messagebox.showerror("読めません", str(e), parent=self)
            return False
        errs, notes = self.book.check_plan(self.app.reg, plan)
        if errs:
            messagebox.showerror("直してください", "\n".join(errs), parent=self)
            return False
        if not quiet:
            messagebox.showinfo("確認", "問題はありません。" + ("\n\n注意:\n" + "\n".join(notes) if notes else ""), parent=self)
        return True

    def save(self):
        if not self.check(quiet=True):
            return
        old = self.path.read_bytes() if self.path.exists() else None
        body = self.text.get("1.0", "end").strip("\n") + "\n"
        self.path.write_text(body, encoding="utf-8", newline="\n")
        self.app.undo.append((self.path, old))
        self.destroy()
        self.app.done("冊子の構成を保存しました（src/book.txt）")


class NewAppendixDialog(tk.Toplevel):
    """別表・別紙・別図を新設する。"""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("別表・別紙・別図を新設")
        self.transient(app)
        place_dialog(self, app)
        self.resizable(False, False)
        f = ttk.Frame(self, padding=12)
        f.pack()
        parents = [d.id for d in app.reg.docs.values() if d.meta.get("appendices") is not None or d.kind in ("規約", "細則", "使用細則")]
        parents.sort(key=lambda i: app.reg.docs[i].kind != "規約")          # 規約を先頭（既定）に
        self.parent_ids = parents
        ttk.Label(f, text="属する文書:").grid(row=0, column=0, sticky="e", pady=4)
        self.parent = ttk.Combobox(f, state="readonly", width=34, values=[app.reg.docs[i].title for i in parents])
        self.parent.current(0)
        self.parent.grid(row=0, column=1, columnspan=2, sticky="w", padx=6)
        ttk.Label(f, text="種類:").grid(row=1, column=0, sticky="e", pady=4)
        self.kind = ttk.Combobox(f, state="readonly", width=10, values=["別表", "別紙", "別図"])
        self.kind.current(1)
        self.kind.grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(f, text="題名:").grid(row=2, column=0, sticky="e", pady=4)
        self.title_e = ttk.Entry(f, width=36)
        self.title_e.grid(row=2, column=1, columnspan=2, sticky="w", padx=6)
        self.mode = tk.StringVar(value="table")
        ttk.Radiobutton(f, text="表を作る", value="table", variable=self.mode, command=self.sync).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        row = ttk.Frame(f)
        row.grid(row=4, column=1, columnspan=2, sticky="w", padx=6)
        self.cols = tk.IntVar(value=3)
        self.rows = tk.IntVar(value=4)
        ttk.Label(row, text="列").pack(side="left")
        self.sp_c = ttk.Spinbox(row, from_=1, to=20, width=4, textvariable=self.cols)
        self.sp_c.pack(side="left", padx=4)
        ttk.Label(row, text="行（見出しを含む）").pack(side="left")
        self.sp_r = ttk.Spinbox(row, from_=1, to=200, width=4, textvariable=self.rows)
        self.sp_r.pack(side="left", padx=4)
        ttk.Radiobutton(f, text="画像（様式・図）を取り込む", value="image", variable=self.mode, command=self.sync).grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.img = tk.StringVar()
        self.img_e = ttk.Entry(f, textvariable=self.img, width=36, state="disabled")
        self.img_e.grid(row=6, column=1, sticky="w", padx=6)
        self.img_b = ttk.Button(f, text="選ぶ…", command=self.pick, state="disabled")
        self.img_b.grid(row=6, column=2)
        ttk.Label(f, text="番号は、同じ種類の次の番号が自動で付きます。表は、作ったあとで「表を編集…」で書き込みます。", style="Hint.TLabel").grid(row=7, column=0, columnspan=3, sticky="w", pady=8)
        bt = ttk.Frame(f)
        bt.grid(row=8, column=0, columnspan=3, sticky="e")
        ttk.Button(bt, text="新設", command=self.ok, style="Accent.TButton").pack(side="right")
        ttk.Button(bt, text="キャンセル", command=self.destroy).pack(side="right", padx=6)

    def sync(self):
        table = self.mode.get() == "table"
        for w in (self.sp_c, self.sp_r):
            w.configure(state="normal" if table else "disabled")
        for w in (self.img_e, self.img_b):
            w.configure(state="disabled" if table else "normal")

    def pick(self):
        p = filedialog.askopenfilename(parent=self, title="画像を選ぶ", filetypes=[("画像", "*.png *.jpg *.jpeg *.gif *.webp")])
        if p:
            self.img.set(p)

    def ok(self):
        image = self.img.get().strip() if self.mode.get() == "image" else None
        if self.mode.get() == "image" and not image:
            messagebox.showerror("新設できません", "取り込む画像を選んでください。", parent=self)
            return
        try:
            ncols, nrows = int(self.cols.get()), int(self.rows.get())
            path, ppath, old_parent = ae.create_appendix(self.app.reg, self.parent_ids[self.parent.current()], self.kind.get(),
                                                         self.title_e.get(), image_file=image, ncols=ncols, nrows=nrows)
        except (ae.AppendixError, ValueError, tk.TclError) as e:
            messagebox.showerror("新設できません", str(e), parent=self)
            return
        self.app.undo.append([(path, None), (ppath, old_parent)])
        self.destroy()
        self.app.after_appendix(path.stem, f"{self.kind.get()}を新設しました")

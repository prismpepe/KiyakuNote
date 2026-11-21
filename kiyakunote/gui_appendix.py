"""別表・別紙・別図を画面で編集するダイアログ（表のセル、新設）。処理本体は appendix_edit。"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import appendix_edit as ae
from .gui_style import place_dialog
from .tables import list_tables

NL = "↵"          # セルの中の改行を、入力欄では ↵ で表す


class TableEditDialog(tk.Toplevel):
    """結合セルのない表を、行・列を足したり消したりしながら編集する（1行目は見出し）。"""

    def __init__(self, app, doc):
        super().__init__(app)
        self.app, self.doc = app, doc
        self.title(f"表を編集 — {doc.title}")
        self.geometry("980x620")
        self.transient(app)
        place_dialog(self, app)
        self.tables = list_tables(doc.raw_body)
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(10, 4))
        self.which = ttk.Combobox(top, state="readonly", width=24,
                                  values=[f"表{i + 1}" + ("（結合セルあり・編集できません）" if t["span"] else "") for i, t in enumerate(self.tables)])
        self.which.current(0)
        self.which.bind("<<ComboboxSelected>>", lambda e: self.load())
        if len(self.tables) > 1:
            ttk.Label(top, text="編集する表:").pack(side="left")
            self.which.pack(side="left", padx=6)
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=4)
        for text, cmd in (("行を追加（下）", self.add_row), ("行を削除", self.del_row), ("列を追加（右）", self.add_col), ("列を削除", self.del_col)):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=3)
        ttk.Label(self, text=f"枠をクリックして書き換えます。1行目は見出しです。セルの中で改行したいところには {NL} を入れます。"
                             "「行を追加／削除」は、いま選んでいる枠の行に対して働きます。", style="Hint.TLabel").pack(anchor="w", padx=10)
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
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        bt = ttk.Frame(self)
        bt.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bt, text="保存", command=self.save, style="Accent.TButton").pack(side="right")
        ttk.Button(bt, text="キャンセル", command=self.destroy).pack(side="right", padx=6)
        self.entries, self.cur = [], (0, 0)
        self.load()

    def index(self):
        return self.which.current() if self.which.current() >= 0 else 0

    def load(self):
        t = self.tables[self.index()]
        for w in self.inner.winfo_children():
            w.destroy()
        self.entries = []
        if t["span"]:
            ttk.Label(self.inner, text="この表は、結合セルがあるので、画面では編集できません。\n"
                                       "テキストエディタで直すか、別の方法（Excelから取り込むなど）を使ってください。").pack(padx=20, pady=20)
            return
        self.rows_to_grid([[c.replace("\n", NL) for c in r] for r in t["rows"]])

    def rows_to_grid(self, rows):
        for w in self.inner.winfo_children():
            w.destroy()
        self.entries = []
        for r, row in enumerate(rows):
            line = []
            for c, text in enumerate(row):
                e = tk.Entry(self.inner, width=22, font=self.app.styler.f_input, relief="solid", borderwidth=1,
                             background="#dbe5f1" if r == 0 else "#ffffff")
                e.insert(0, text)
                e.grid(row=r, column=c, sticky="nsew")
                e.bind("<FocusIn>", lambda ev, rr=r, cc=c: setattr(self, "cur", (rr, cc)))
                e.bind("<MouseWheel>", lambda ev: self.canvas.yview_scroll(-1 if ev.delta > 0 else 1, "units"))
                line.append(e)
            self.entries.append(line)

    def values(self):
        return [[e.get() for e in line] for line in self.entries]

    def add_row(self):
        rows = self.values()
        if not rows:
            return
        r = min(self.cur[0], len(rows) - 1)
        rows.insert(r + 1, [""] * len(rows[0]))
        self.rows_to_grid(rows)
        self.cur = (r + 1, self.cur[1])

    def del_row(self):
        rows = self.values()
        if len(rows) <= 1:
            messagebox.showinfo("行を削除", "見出しの行だけになるので、削除できません。", parent=self)
            return
        r = min(self.cur[0], len(rows) - 1)
        del rows[r]
        self.rows_to_grid(rows)
        self.cur = (min(r, len(rows) - 1), self.cur[1])

    def add_col(self):
        rows = self.values()
        if not rows:
            return
        c = min(self.cur[1], len(rows[0]) - 1)
        for r in rows:
            r.insert(c + 1, "")
        self.rows_to_grid(rows)
        self.cur = (self.cur[0], c + 1)

    def del_col(self):
        rows = self.values()
        if not rows or len(rows[0]) <= 1:
            messagebox.showinfo("列を削除", "1列だけになるので、削除できません。", parent=self)
            return
        c = min(self.cur[1], len(rows[0]) - 1)
        for r in rows:
            del r[c]
        self.rows_to_grid(rows)
        self.cur = (self.cur[0], min(c, len(rows[0]) - 1))

    def save(self):
        if not self.entries:
            self.destroy()
            return
        rows = [[c.replace(NL, "\n") for c in r] for r in self.values()]
        path = Path(self.doc.path)
        old = path.read_bytes()
        try:
            ae.save_table(path, self.index(), rows)
        except ae.AppendixError as e:
            messagebox.showerror("保存できません", str(e), parent=self)
            return
        self.app.undo.append((path, old))
        self.destroy()
        self.app.after_appendix(self.doc.id, "表を保存しました")


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

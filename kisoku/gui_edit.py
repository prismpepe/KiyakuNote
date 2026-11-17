"""GUIの編集ダイアログ（条の変更・新設・参照の挿入）。処理本体は kisoku.edit。"""
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import edit
from .core import Article, Registry, load_dir
from .render import article_text
from .search import search, snippet

HELP = ("1行が1つの項・号です。行頭の語: 項（第1項・第2項…）／号（（１）…）／細（ア．…）／目（（ア）…）。\n"
        "{#…} はIDなので変えないでください（新しい行は省略できます）。他の条を指すときは「参照を挿入」を使います（番号は自動で付きます）。")


class RefPicker(tk.Toplevel):
    """参照先を検索して選び、{ref:…} を作る。"""

    def __init__(self, app, doc_id, on_pick):
        super().__init__(app)
        self.app, self.doc_id, self.on_pick, self.hits = app, doc_id, on_pick, {}
        self.title("参照を挿入")
        self.geometry("820x460")
        self.transient(app)
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)
        ttk.Label(top, text="参照先の語（条名・本文の一部）:").pack(side="left")
        self.q = ttk.Entry(top, width=30)
        self.q.pack(side="left", padx=4)
        self.q.bind("<Return>", lambda e: self.find())
        self.q.focus_set()
        ttk.Button(top, text="探す", command=self.find).pack(side="left")
        self.tree = ttk.Treeview(self, columns=("d", "l", "t"), show="headings", height=14, selectmode="browse")
        for c, t, w in (("d", "文書", 200), ("l", "条・項・号", 150), ("t", "抜粋", 420)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8)
        self.tree.bind("<Double-1>", lambda e: self.pick())
        opt = ttk.Frame(self)
        opt.pack(fill="x", padx=8, pady=6)
        self.rel = tk.BooleanVar()
        self.ttl = tk.BooleanVar()
        ttk.Checkbutton(opt, text="直前・直後なら「前条」「前項」「次条」と表記する", variable=self.rel).pack(anchor="w")
        ttk.Checkbutton(opt, text="条名を付ける（例: 第19条（専有部分の貸与））", variable=self.ttl).pack(anchor="w")
        bt = ttk.Frame(self)
        bt.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bt, text="挿入", command=self.pick).pack(side="right")
        ttk.Button(bt, text="閉じる", command=self.destroy).pack(side="right", padx=6)

    def find(self):
        q = self.q.get().strip()
        if not q:
            return
        self.tree.delete(*self.tree.get_children())
        self.hits = {}
        for title, did, label, art_title, text, level, nid in search(self.app.db, q, limit=200):
            head = label + (f"（{art_title}）" if level == "article" and art_title else "")
            iid = self.tree.insert("", "end", values=(title, head, snippet(text or art_title, q, 40)))
            self.hits[iid] = (did, nid, level)

    def pick(self):
        sel = self.tree.selection()
        if not sel:
            return
        did, nid, level = self.hits[sel[0]]
        target = did if level == "appendix" else (nid if did == self.doc_id else f"{did}#{nid}")
        opts = ("|rel" if self.rel.get() else "") + ("|title" if self.ttl.get() else "")
        self.on_pick("{ref:" + target + opts + "}")
        self.destroy()


class EditDialog(tk.Toplevel):
    """条の変更、または新設。art が None なら新設。"""

    def __init__(self, app, doc_id, art=None, after_id=""):
        super().__init__(app)
        self.app, self.doc_id, self.art_id = app, doc_id, (art.id if art else None)
        self.new = art is None
        doc = app.reg.docs[doc_id]
        self.title(("条を新設" if self.new else f"条を変更: {art.label}") + f"　{doc.title}")
        self.geometry("900x700")
        self.transient(app)
        f = ttk.Frame(self)
        f.pack(fill="x", padx=10, pady=8)
        if self.new:
            ttk.Label(f, text="この条の前（直前の条）:").grid(row=0, column=0, sticky="w")
            self.arts = [a for a in doc.elements if isinstance(a, Article)]
            names = ["（先頭）"] + [f"{a.label}（{a.title}）" if a.title else a.label for a in self.arts]
            self.after_cb = ttk.Combobox(f, values=names, state="readonly", width=46)
            idx = next((i + 1 for i, a in enumerate(self.arts) if a.id == after_id), len(names) - 1)
            self.after_cb.current(idx)
            self.after_cb.grid(row=0, column=1, sticky="w", padx=6)
            self.branch = tk.BooleanVar()
            ttk.Checkbutton(f, text="枝番にする（直前の条の「第N条の2」。以降の条番号は動かない）",
                            variable=self.branch).grid(row=1, column=1, sticky="w", padx=6, pady=2)
            ttk.Label(f, text="ID（英数字とハイフン）:").grid(row=2, column=0, sticky="w")
            self.id_var = tk.StringVar(value=edit.gen_article_id(edit.load_for_edit(doc.path)))
            ttk.Entry(f, textvariable=self.id_var, width=30).grid(row=2, column=1, sticky="w", padx=6)
        ttk.Label(f, text="見出し:").grid(row=3, column=0, sticky="w", pady=4)
        self.title_var = tk.StringVar(value=art.title if art else "")
        ttk.Entry(f, textvariable=self.title_var, width=50).grid(row=3, column=1, sticky="w", padx=6)
        ttk.Label(self, text=HELP, foreground="#555", justify="left").pack(anchor="w", padx=10)
        self.ed = tk.Text(self, wrap="char", font=("MS Gothic", 10), height=14, undo=True, padx=6, pady=4)
        self.ed.pack(fill="both", expand=True, padx=10, pady=4)
        self.ed.insert("1.0", edit.article_to_text(art) if art else "項 ")
        bt = ttk.Frame(self)
        bt.pack(fill="x", padx=10)
        ttk.Button(bt, text="参照を挿入…", command=self.insert_ref).pack(side="left")
        ttk.Button(bt, text="出力のプレビュー", command=self.preview).pack(side="left", padx=6)
        ttk.Button(bt, text="キャンセル", command=self.destroy).pack(side="right")
        ttk.Button(bt, text="保存", command=self.save).pack(side="right", padx=6)
        ttk.Label(self, text="プレビュー（番号・参照を展開した出力）:").pack(anchor="w", padx=10, pady=(8, 0))
        self.pv = tk.Text(self, wrap="word", font=("Yu Mincho", 10), height=9, state="disabled", padx=6)
        self.pv.pack(fill="x", padx=10, pady=(0, 10))

    def insert_ref(self):
        RefPicker(self.app, self.doc_id, lambda tok: (self.ed.insert("insert", tok), self.ed.focus_set()))

    def _apply(self, doc):
        """編集内容を doc に反映する。エラーなら (errors, None)。"""
        text = self.ed.get("1.0", "end").strip("\n")
        if self.new:
            sel = self.after_cb.current()
            after = self.arts[sel - 1].id if sel > 0 else ""
            errs, art = edit.add_article(doc, after, self.title_var.get(), text,
                                         branch=self.branch.get(), new_id=self.id_var.get().strip())
            return errs, (art.id if art else None)
        return edit.edit_article(doc, self.art_id, self.title_var.get(), text), self.art_id

    def preview(self):
        """作業用コピーに反映して、番号・参照を展開した結果を見せる。"""
        tmp = Path(self.app.tmp) / "preview"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir()
        for p in Path(self.app.reg.docs[self.doc_id].path).parent.glob("*.md"):
            shutil.copy(p, tmp / p.name)
        doc = edit.load_for_edit(tmp / Path(self.app.reg.docs[self.doc_id].path).name)
        errs, aid = self._apply(doc)
        self.pv.config(state="normal")
        self.pv.delete("1.0", "end")
        if errs:
            self.pv.insert("1.0", "\n".join(errs))
        else:
            edit.save(doc)
            reg = Registry(load_dir(tmp))
            d = reg.docs[self.doc_id]
            art = next(a for a in d.articles if a.id == aid)
            try:
                self.pv.insert("1.0", article_text(reg, d, art))
            except Exception as e:                              # noqa: BLE001
                self.pv.insert("1.0", f"展開できません: {e}")
        self.pv.config(state="disabled")

    def save(self):
        path = Path(self.app.reg.docs[self.doc_id].path)
        old = path.read_bytes()
        doc = edit.load_for_edit(path)
        errs, aid = self._apply(doc)
        if errs:
            messagebox.showerror("保存できません", "\n".join(errs), parent=self)
            return
        edit.save(doc)
        self.app.undo.append((path, old))
        self.destroy()
        self.app.after_edit(self.doc_id, aid)

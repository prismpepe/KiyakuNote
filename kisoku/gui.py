"""Windows のGUI（Tkinter）。検索・条文の閲覧・整合性チェック・新旧対照表・Word出力・版の一覧。

起動: python -m kisoku gui  （または 管理規約システム.pyw をダブルクリック）
画面の操作はすべて、コマンドラインと同じ処理（kisoku の各モジュール）を呼ぶ。
"""
import re
import subprocess
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .compare import KINDS, appendix_changes, bare_reference_notes, compare_doc, render_bare_notes, render_table
from .core import APPENDIX_KINDS, Heading
from .lint import lint
from .render import article_text, render_doc
from .search import build_index, doc_order, plain, refs_of, search, snippet
from .versions import ROOT, load_revisions, load_version
from . import gitops

FONT = ("Yu Gothic UI", 10)
MONO = ("MS Gothic", 10)
WORK = "作業中の src/（未確定の編集を含む）"

LINT_HELP = {
    "E-DUP-ID": "IDが重複している",
    "E-DUP-DOC": "文書IDが重複している",
    "E-REF": "参照先が存在しない",
    "E-DELETED": "削除済みの条を参照している",
    "E-APPENDIX": "別表・別紙の登録に誤りがある",
    "W-BARE-NUM": "条番号が本文に直書きされている（番号が変わると誤りになる）",
    "W-BARE-REL": "前条・前項などが本文に直書きされている",
    "W-NOID": "条にIDがない",
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("マンション管理規約システム")
        self.geometry("1180x760")
        self.option_add("*Font", FONT)
        ttk.Style(self).configure("Treeview", rowheight=22, font=FONT)
        self.revs = load_revisions()
        self.versions = {WORK: "WORKTREE"}
        for r in self.revs:
            if r.get("ref"):
                self.versions[f"{r['effective']} 施行（{r['ref']}）"] = r["ref"]
        self.reg = None
        self.db = None
        self.tmp = Path(tempfile.mkdtemp(prefix="kisoku-gui-"))
        self.repo = ROOT
        self.undo = []                  # 保存前のファイル内容 [(パス, 内容)]。元に戻す用
        self.cmp_rows = []
        self.cmp_notes = []
        self.cmp_labels = ("", "")
        self.status = tk.StringVar(value="")
        self._top()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=(0, 2))
        self.tab_read = self._tab_read()
        self.tab_search = self._tab_search()
        self.tab_lint = self._tab_lint()
        self.tab_cmp = self._tab_cmp()
        self.tab_out = self._tab_out()
        self.tab_rev = self._tab_rev()
        for t, name in ((self.tab_read, "条文"), (self.tab_search, "検索"), (self.tab_lint, "整合性チェック"),
                        (self.tab_cmp, "新旧対照表"), (self.tab_out, "Word出力"), (self.tab_rev, "版の一覧")):
            self.nb.add(t, text=f"  {name}  ")
        ttk.Label(self, textvariable=self.status, anchor="w", relief="sunken").pack(fill="x", side="bottom")
        self.fill_revs()
        self.update_git_state()
        self.load_version()

    # ---- 共通 ----
    def busy(self, msg):
        self.status.set(msg)
        self.config(cursor="watch")
        self.update_idletasks()

    def done(self, msg=""):
        self.status.set(msg)
        self.config(cursor="")

    def _top(self):
        f = ttk.Frame(self)
        f.pack(fill="x", padx=6, pady=6)
        ttk.Label(f, text="表示する版:").pack(side="left")
        self.ver = ttk.Combobox(f, values=list(self.versions), state="readonly", width=44)
        self.ver.set(WORK)
        self.ver.pack(side="left", padx=4)
        self.ver.bind("<<ComboboxSelected>>", lambda e: self.load_version())
        ttk.Button(f, text="読み直す", command=self.load_version).pack(side="left", padx=4)

    def load_version(self):
        ref = self.versions[self.ver.get()]
        self.busy("読み込み中…")
        try:
            self.reg = load_version(ref)
            self.db = self.tmp / f"idx-{re.sub(r'[^A-Za-z0-9]', '_', ref)}.db"
            n = build_index(self.reg, self.db)
        except Exception as e:                                  # noqa: BLE001
            self.done("")
            messagebox.showerror("読み込めません", str(e))
            return
        self.fill_tree()
        names = ["（すべて）"] + [d.title for d in sorted(self.reg.docs.values(), key=doc_order)
                                   if d.kind not in APPENDIX_KINDS]
        self.s_doc["values"] = names
        self.s_doc.set(names[0])
        self.out_doc["values"] = names
        self.out_doc.set(names[0])
        self.done(f"{self.ver.get()} を読み込みました（文書 {len(self.reg.docs)} 件、索引 {n} 行）")

    # ---- 条文 ----
    def _tab_read(self):
        f = ttk.Frame(self.nb)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(6, 4))
        ttk.Button(bar, text="この条を変更…", command=self.edit_selected).pack(side="left", padx=2)
        ttk.Button(bar, text="条を新設…", command=self.new_article).pack(side="left", padx=2)
        ttk.Button(bar, text="この条を削除…", command=self.delete_selected).pack(side="left", padx=2)
        ttk.Button(bar, text="直前の保存を元に戻す", command=self.undo_last).pack(side="left", padx=14)
        ttk.Label(bar, text="（編集は「作業中の src/」を表示しているときだけできます）", foreground="#555").pack(side="left")
        pw = ttk.PanedWindow(f, orient="horizontal")
        pw.pack(fill="both", expand=True)
        left = ttk.Frame(pw)
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        sb = ttk.Scrollbar(left, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree)
        right = ttk.Frame(pw)
        self.body = tk.Text(right, wrap="word", font=("Yu Mincho", 11), height=18, padx=8, pady=6)
        sb2 = ttk.Scrollbar(right, command=self.body.yview)
        self.body.configure(yscrollcommand=sb2.set, state="disabled")
        self.body.pack(side="top", fill="both", expand=True)
        ttk.Label(right, text="この条が参照している先／この条を参照している元").pack(anchor="w", pady=(6, 0))
        self.refs_box = tk.Text(right, wrap="word", height=8, state="disabled", padx=8)
        self.refs_box.pack(side="top", fill="x")
        pw.add(left, weight=1)
        pw.add(right, weight=3)
        return f

    def fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        for d in sorted(self.reg.docs.values(), key=doc_order):
            self.tree.insert("", "end", iid=d.id, text=f"{d.title}（{d.kind}）")
            if d.kind in APPENDIX_KINDS:
                continue
            parent = d.id
            for el in d.elements:
                if isinstance(el, Heading):
                    if el.kind == "supplementary":
                        t = "附則"
                    elif el.kind == "section":
                        t = f"第{el.number}節 {el.title}"
                    elif el.title.strip() == "本則":
                        parent = d.id
                        continue
                    else:
                        t = f"第{el.number}章 {el.title}"
                    parent = self.tree.insert(d.id, "end", iid=f"{d.id}|h|{el.id or el.line}", text=t)
                    continue
                label = f"{el.label}　削除" if el.deleted else f"{el.label}（{el.title}）" if el.title else el.label
                self.tree.insert(parent, "end", iid=f"{d.id}|{el.id}", text=label)

    def set_text(self, widget, text):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.config(state="disabled")

    def on_tree(self, _=None):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        if "|h|" in iid:
            return
        if "|" not in iid:
            d = self.reg.docs[iid]
            if d.kind in APPENDIX_KINDS:
                self.show_appendix(d)
            else:
                self.set_text(self.body, render_doc(self.reg, d))
                self.set_text(self.refs_box, "")
            return
        did, aid = iid.split("|", 1)
        d = self.reg.docs[did]
        art = next((a for a in d.articles if a.id == aid), None)
        if art is None:
            return
        self.set_text(self.body, article_text(self.reg, d, art))
        out, inc = refs_of(self.db, f"{did}#{aid}")
        lines = ["【参照している先】"] + [f"  {a} → {c}" for a, _, c in out] if out else ["【参照している先】  なし"]
        lines += ["【参照している元】"] + [f"  {self.reg.docs[x].title} {y} → {z}" for x, y, z in inc] if inc else ["【参照している元】  なし"]
        self.set_text(self.refs_box, "\n".join(lines))

    def show_appendix(self, d):
        n = self.reg.appendix_no(d)
        label = "別図" if d.kind == "別図" else (f"別表第{n}" if d.kind == "別表" else f"{d.kind}{n}")
        if d.meta.get("deleted") == "true":
            text = f"{label}（削除）"
        elif "<tr" in d.raw_body:
            rows = []
            for tr in re.findall(r"<tr>(.*?)</tr>", d.raw_body, re.S):
                cells = [plain(c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
                rows.append(" | ".join(cells))
            text = f"{label}　{d.title}\n\n" + "\n".join(rows)
        else:
            text = f"{label}　{d.title}\n\n" + (
                "（画像のページです。Word出力でPDFのページ画像が付きます）" if "![" in d.raw_body else d.raw_body)
        self.set_text(self.body, text)
        self.set_text(self.refs_box, "")

    # ---- 編集 ----
    def selected_article(self):
        """ツリーで選んでいる条を (文書ID, Article) で返す。条でなければ (文書ID, None)。"""
        sel = self.tree.selection()
        if not sel or "|h|" in sel[0]:
            return (sel[0].split("|")[0] if sel else None), None
        if "|" not in sel[0]:
            return sel[0], None
        did, aid = sel[0].split("|", 1)
        return did, next((a for a in self.reg.docs[did].articles if a.id == aid), None)

    def can_edit(self):
        if self.versions[self.ver.get()] != "WORKTREE":
            messagebox.showinfo("編集できません", "編集できるのは「作業中の src/」を表示しているときだけです。")
            return False
        return True

    def edit_selected(self):
        if not self.can_edit():
            return
        did, art = self.selected_article()
        if art is None:
            messagebox.showinfo("条を選んでください", "左の一覧で、変更する条を選んでください。")
            return
        from .gui_edit import EditDialog
        EditDialog(self, did, art)

    def new_article(self):
        if not self.can_edit():
            return
        did, art = self.selected_article()
        if did is None or self.reg.docs[did].kind in APPENDIX_KINDS:
            messagebox.showinfo("文書を選んでください", "左の一覧で、新設する文書（規約・細則）の条を選んでください。")
            return
        from .gui_edit import EditDialog
        EditDialog(self, did, None, after_id=art.id if art else "")

    def delete_selected(self):
        if not self.can_edit():
            return
        did, art = self.selected_article()
        if art is None:
            messagebox.showinfo("条を選んでください", "左の一覧で、削除する条を選んでください。")
            return
        if art.deleted:
            return
        msg = (f"{art.label}（{art.title}）を削除します。\n"
               f"番号の枠とIDは残り、「{art.label}　削除」と表示されます。\n"
               "この条を参照している箇所は、整合性チェックでエラーになります。")
        if not messagebox.askyesno("条の削除", msg):
            return
        from . import edit
        path = Path(self.reg.docs[did].path)
        old = path.read_bytes()
        doc = edit.load_for_edit(path)
        edit.delete_article(doc, art.id)
        edit.save(doc)
        self.undo.append((path, old))
        self.after_edit(did, art.id)

    def undo_last(self):
        if not self.undo:
            messagebox.showinfo("元に戻す", "元に戻せる保存がありません。")
            return
        path, old = self.undo.pop()
        path.write_bytes(old)
        self.load_version()
        self.done(f"元に戻しました: {path.name}")

    def after_edit(self, did, art_id):
        """保存のあとに読み直し、チェックの結果を状態欄に出す。"""
        self.load_version()
        found = lint(self.reg)
        e = sum(1 for f in found if f[0] == "E")
        if art_id:
            self.goto(did, art_id)
        self.update_git_state()
        self.done(f"保存しました。整合性チェック: エラー {e} 件、警告 {len(found) - e} 件" +
                  ("（「整合性チェック」タブで確認してください）" if e else ""))
        if e:
            self.do_lint()

    def goto(self, did, node_id):
        """検索結果などから、条文タブの該当位置へ。"""
        loc = self.reg.find(did, node_id)
        iid = did
        if loc is not None and loc.article is not None:
            iid = f"{did}|{loc.article.id}"
        if not self.tree.exists(iid):
            iid = did
        self.nb.select(self.tab_read)
        self.tree.selection_set(iid)
        self.tree.see(iid)
        self.on_tree()

    # ---- 検索 ----
    def _tab_search(self):
        f = ttk.Frame(self.nb)
        top = ttk.Frame(f)
        top.pack(fill="x", pady=6)
        ttk.Label(top, text="検索語（空白でAND）:").pack(side="left")
        self.s_q = ttk.Entry(top, width=34)
        self.s_q.pack(side="left", padx=4)
        self.s_q.bind("<Return>", lambda e: self.do_search())
        ttk.Label(top, text="文書:").pack(side="left", padx=(10, 0))
        self.s_doc = ttk.Combobox(top, state="readonly", width=26)
        self.s_doc.pack(side="left", padx=4)
        ttk.Button(top, text="検索", command=self.do_search).pack(side="left", padx=6)
        self.s_info = ttk.Label(top, text="")
        self.s_info.pack(side="left", padx=8)
        cols = ("doc", "label", "text")
        self.s_tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        for c, t, w in (("doc", "文書", 220), ("label", "条・項・号", 170), ("text", "抜粋", 700)):
            self.s_tree.heading(c, text=t)
            self.s_tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(f, command=self.s_tree.yview)
        self.s_tree.configure(yscrollcommand=sb.set)
        self.s_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.s_tree.bind("<Double-1>", self.on_search_open)
        self.s_hits = {}
        return f

    def do_search(self):
        q = self.s_q.get().strip()
        if not q:
            return
        doc = None
        if self.s_doc.get() != "（すべて）":
            doc = next((d.id for d in self.reg.docs.values() if d.title == self.s_doc.get()), None)
        rows = search(self.db, q, doc=doc, limit=300)
        self.s_tree.delete(*self.s_tree.get_children())
        self.s_hits = {}
        for i, (title, did, label, art_title, text, level, nid) in enumerate(rows):
            head = label + (f"（{art_title}）" if level == "article" and art_title else "")
            iid = self.s_tree.insert("", "end", values=(title, head, snippet(text or art_title, q, 50)))
            self.s_hits[iid] = (did, nid)
        self.s_info.config(text=f"{len(rows)}件" + ("（上限300）" if len(rows) >= 300 else "") + "　ダブルクリックで条文を開く")

    def on_search_open(self, _=None):
        sel = self.s_tree.selection()
        if sel:
            self.goto(*self.s_hits[sel[0]])

    # ---- 整合性チェック ----
    def _tab_lint(self):
        f = ttk.Frame(self.nb)
        top = ttk.Frame(f)
        top.pack(fill="x", pady=6)
        ttk.Button(top, text="チェックを実行", command=self.do_lint).pack(side="left")
        self.l_info = ttk.Label(top, text="")
        self.l_info.pack(side="left", padx=10)
        cols = ("sev", "code", "doc", "line", "msg")
        self.l_tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        for c, t, w in (("sev", "種別", 60), ("code", "コード", 110), ("doc", "文書", 220), ("line", "行", 60),
                        ("msg", "内容", 600)):
            self.l_tree.heading(c, text=t)
            self.l_tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(f, command=self.l_tree.yview)
        self.l_tree.configure(yscrollcommand=sb.set)
        self.l_tree.pack(side="top", fill="both", expand=True)
        self.l_tree.tag_configure("E", foreground="#b00020")
        self.l_tree.tag_configure("W", foreground="#8a5a00")
        ttk.Label(f, text="E=エラー（直さないと出力できない）／W=警告（原文はそのままで、確認が必要）", foreground="#555").pack(anchor="w", pady=4)
        return f

    def do_lint(self):
        self.busy("チェック中…")
        found = lint(self.reg)
        self.l_tree.delete(*self.l_tree.get_children())
        for sev, code, msg, did, line in found:
            self.l_tree.insert("", "end", tags=(sev,), values=(
                "エラー" if sev == "E" else "警告", code, self.reg.docs[did].title, line, f"{msg}（{LINT_HELP.get(code, '')}）"
                if LINT_HELP.get(code) and code.startswith("W-BARE") else msg))
        e = sum(1 for f in found if f[0] == "E")
        self.l_info.config(text=f"エラー {e} 件、警告 {len(found) - e} 件")
        self.done("チェックを実行しました")

    # ---- 新旧対照表 ----
    def _tab_cmp(self):
        f = ttk.Frame(self.nb)
        top = ttk.Frame(f)
        top.pack(fill="x", pady=6)
        vals = [v for v in self.versions]
        ttk.Label(top, text="改正前:").pack(side="left")
        self.c_old = ttk.Combobox(top, values=vals, state="readonly", width=34)
        self.c_old.set(vals[-1] if len(vals) > 1 else vals[0])   # 既定の改正前: 条文を持つ最新の版
        self.c_old.pack(side="left", padx=4)
        ttk.Label(top, text="改正後:").pack(side="left", padx=(8, 0))
        self.c_new = ttk.Combobox(top, values=vals, state="readonly", width=34)
        self.c_new.set(vals[0])
        self.c_new.pack(side="left", padx=4)
        ttk.Button(top, text="対照表を作る", command=self.do_compare).pack(side="left", padx=8)
        top2 = ttk.Frame(f)
        top2.pack(fill="x")
        self.c_info = ttk.Label(top2, text="（作業中の src/ を編集したあと、「改正後」を作業中にして作ります）", foreground="#555")
        self.c_info.pack(side="left")
        ttk.Button(top2, text="Wordで保存", command=lambda: self.save_cmp("docx")).pack(side="right", padx=2)
        ttk.Button(top2, text="Markdownで保存", command=lambda: self.save_cmp("md")).pack(side="right", padx=2)
        pw = ttk.PanedWindow(f, orient="vertical")
        pw.pack(fill="both", expand=True, pady=4)
        cols = ("kind", "doc", "art")
        self.c_tree = ttk.Treeview(pw, columns=cols, show="headings", selectmode="browse", height=9)
        for c, t, w in (("kind", "区分", 130), ("doc", "文書", 300), ("art", "条", 500)):
            self.c_tree.heading(c, text=t)
            self.c_tree.column(c, width=w, anchor="w")
        self.c_tree.bind("<<TreeviewSelect>>", self.on_cmp_select)
        pw.add(self.c_tree, weight=1)
        pair = ttk.Frame(pw)
        self.c_o = self._mk_text(pair, "改正前")
        self.c_n = self._mk_text(pair, "改正後")
        pw.add(pair, weight=2)
        return f

    def _mk_text(self, parent, title):
        fr = ttk.LabelFrame(parent, text=title)
        fr.pack(side="left", fill="both", expand=True, padx=2)
        t = tk.Text(fr, wrap="word", font=("Yu Mincho", 10), state="disabled", padx=6, pady=4)
        sb = ttk.Scrollbar(fr, command=t.yview)
        t.configure(yscrollcommand=sb.set)
        t.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        t.tag_configure("del", foreground="#c00000", overstrike=True)
        t.tag_configure("ins", foreground="#0032a0", underline=True, font=("Yu Mincho", 10, "bold"))
        return t

    def put_marked(self, widget, s):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        for part in re.split(r"(~~.*?~~|\*\*.*?\*\*)", s, flags=re.S):
            if len(part) > 4 and part.startswith("~~") and part.endswith("~~"):
                widget.insert("end", part[2:-2], "del")
            elif len(part) > 4 and part.startswith("**") and part.endswith("**"):
                widget.insert("end", part[2:-2], "ins")
            else:
                widget.insert("end", part)
        widget.config(state="disabled")

    def do_compare(self):
        old, new = self.versions[self.c_old.get()], self.versions[self.c_new.get()]
        if old == new:
            messagebox.showinfo("対照表", "改正前と改正後が同じ版です。")
            return
        self.busy("対照表を作っています…")
        try:
            ro, rn = load_version(old), load_version(new)
        except Exception as e:                                  # noqa: BLE001
            self.done("")
            messagebox.showerror("読み込めません", str(e))
            return
        self.cmp_regs = (ro, rn)
        self.cmp_labels = (self.c_old.get(), self.c_new.get())
        self.cmp_rows, total = [], {k: 0 for k in KINDS}
        ids = [i for i, d in rn.docs.items() if d.kind not in APPENDIX_KINDS]
        ids += [i for i in ro.docs if i not in ids and ro.docs[i].kind not in APPENDIX_KINDS]
        for did in ids:
            for kind, to, tn in compare_doc(ro, rn, did):
                head = (tn if kind != "削除" else to).split("\n")[0]
                head = re.sub(r"~~|\*\*", "", head)
                self.cmp_rows.append((kind, (rn.docs.get(did) or ro.docs[did]).title, head, to, tn))
                total[kind] += 1
        self.cmp_notes = bare_reference_notes(rn)
        self.cmp_ap = appendix_changes(ro, rn)
        self.c_tree.delete(*self.c_tree.get_children())
        for i, (kind, title, head, _, _) in enumerate(self.cmp_rows):
            self.c_tree.insert("", "end", iid=str(i), values=(kind, title, head))
        s = "、".join(f"{k} {v}件" for k, v in total.items() if v) or "変更なし"
        extra = f"　別表・別紙 {len(self.cmp_ap)}件" if self.cmp_ap else ""
        warn = f"　／　要確認の直書き参照 {len(self.cmp_notes)}件（保存した対照表の末尾に載ります）" if self.cmp_notes else ""
        self.c_info.config(text=s + extra + warn, foreground="#000")
        self.put_marked(self.c_o, "")
        self.put_marked(self.c_n, "")
        self.done("対照表を作りました")

    def on_cmp_select(self, _=None):
        sel = self.c_tree.selection()
        if sel:
            kind, title, head, to, tn = self.cmp_rows[int(sel[0])]
            self.put_marked(self.c_o, to)
            self.put_marked(self.c_n, tn)

    def save_cmp(self, fmt):
        if not self.cmp_labels[0]:
            messagebox.showinfo("保存", "先に「対照表を作る」を押してください。")
            return
        ro, rn = self.cmp_regs
        path = filedialog.asksaveasfilename(defaultextension=f".{fmt}", initialfile=f"新旧対照表.{fmt}",
                                            filetypes=[("Word" if fmt == "docx" else "Markdown", f"*.{fmt}")])
        if not path:
            return
        self.busy("保存中…")
        lo, ln = self.cmp_labels
        if fmt == "docx":
            from .docx_out import build_compare_docx
            build_compare_docx(ro, rn, lo, ln, path, notes=self.cmp_notes)
        else:
            Path(path).write_text(render_table(ro, rn, lo, ln) + "\n" + render_bare_notes(self.cmp_notes),
                                  encoding="utf-8", newline="\n")
        self.done(f"保存しました: {path}")
        self.open_path(path)

    # ---- Word出力 ----
    def _tab_out(self):
        f = ttk.Frame(self.nb)
        box = ttk.LabelFrame(f, text="規約・細則をWordに出力")
        box.pack(fill="x", padx=10, pady=14)
        row = ttk.Frame(box)
        row.pack(fill="x", padx=10, pady=10)
        ttk.Label(row, text="出力する文書:").pack(side="left")
        self.out_doc = ttk.Combobox(row, state="readonly", width=40)
        self.out_doc.pack(side="left", padx=6)
        ttk.Button(row, text="Wordで出力…", command=self.do_docx).pack(side="left", padx=10)
        ttk.Label(box, text="番号は計算済み、参照は展開済み。別表・別紙（画像を含む）は規約の末尾に付きます。\n"
                            "整合性チェックでエラーがあると出力できません。",
                  foreground="#555").pack(anchor="w", padx=10, pady=(0, 10))
        return f

    def do_docx(self):
        errors = [f for f in lint(self.reg) if f[0] == "E"]
        if errors:
            messagebox.showerror("出力できません", f"整合性チェックにエラーが {len(errors)} 件あります。先に直してください。")
            return
        which = self.out_doc.get()
        docs = [d for d in sorted(self.reg.docs.values(), key=doc_order)
                if d.kind not in APPENDIX_KINDS and (which == "（すべて）" or d.title == which)]
        folder = filedialog.askdirectory(title="出力先のフォルダ")
        if not folder:
            return
        from .docx_out import build_docx
        src_dir = ROOT / "src"
        if self.versions[self.ver.get()] != "WORKTREE":
            src_dir = self.tmp / "assets-src"
            src_dir.mkdir(exist_ok=True)
            self._copy_assets(src_dir)
        self.busy("Wordを出力中…")
        for d in docs:
            build_docx(self.reg, d, Path(folder) / f"{d.title}.docx", src_dir=src_dir)
        self.done(f"{len(docs)} 件を出力しました: {folder}")
        self.open_path(folder)

    def _copy_assets(self, dest):
        """過去の版の画像は gitから取り出す。無ければ作業中のsrc/の画像を使う。"""
        import shutil
        src = ROOT / "src" / "assets"
        if src.exists():
            shutil.copytree(src, dest / "assets", dirs_exist_ok=True)

    # ---- 版の一覧 ----
    def _tab_rev(self):
        f = ttk.Frame(self.nb)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(6, 0))
        ttk.Button(bar, text="変更を記録…", command=self.record_changes).pack(side="left", padx=2)
        ttk.Button(bar, text="新しい版として登録…", command=self.register_version).pack(side="left", padx=2)
        self.git_state = ttk.Label(bar, text="", foreground="#555")
        self.git_state.pack(side="left", padx=12)
        cols = ("res", "eff", "ref", "n")
        self.r_tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse", height=12)
        for c, t, w in (("res", "総会決議日", 110), ("eff", "施行日", 110), ("ref", "条文を持つ版", 200), ("n", "改定件数", 80)):
            self.r_tree.heading(c, text=t)
            self.r_tree.column(c, width=w, anchor="w")
        self.r_tree.pack(fill="x", pady=6)
        self.r_tree.bind("<<TreeviewSelect>>", self.on_rev)
        self.r_text = tk.Text(f, wrap="word", state="disabled", height=14, padx=8)
        self.r_text.pack(fill="both", expand=True)
        ttk.Label(f, text="条文を持つ版は、「表示する版」や新旧対照表で選べます。記録のみの版は、その時点の規約を取り込むと選べるようになります。",
                  foreground="#555").pack(anchor="w", pady=4)
        return f

    def fill_revs(self):
        self.r_tree.delete(*self.r_tree.get_children())
        for i, r in enumerate(self.revs):
            self.r_tree.insert("", "end", iid=str(i), values=(r["resolution"], r["effective"] or "—",
                                                              r.get("ref") or "（記録のみ）", len(r["changes"])))

    def update_git_state(self):
        try:
            n = len(gitops.changed_files(self.repo)) if gitops.is_repo(self.repo) else None
        except gitops.GitError:
            n = None
        self.git_state.config(text="（git が使えません）" if n is None else
                              f"未記録の変更: {n} 件" if n else "未記録の変更はありません")

    def record_changes(self):
        try:
            files = gitops.changed_files(self.repo)
        except gitops.GitError as e:
            messagebox.showerror("git が使えません", str(e))
            return
        if not files:
            messagebox.showinfo("変更を記録", "記録する変更がありません。")
            return
        from .gui_git import CommitDialog
        CommitDialog(self, files)

    def register_version(self):
        try:
            if not gitops.is_repo(self.repo):
                raise gitops.GitError("このフォルダは git の管理下にありません")
            base = [r for r in self.revs if r.get("ref")]
            if not base:
                raise gitops.GitError("比べる元になる、条文を持つ版がありません")
            last = max(base, key=lambda r: r["effective"])
            self.busy("改定内容の下書きを作っています…")
            sug = gitops.suggest_changes(load_version(last["ref"]), load_version("WORKTREE"))
            self.done("")
        except Exception as e:                                   # noqa: BLE001
            self.done("")
            messagebox.showerror("登録できません", str(e))
            return
        from .gui_git import RegisterDialog
        RegisterDialog(self, sug)

    def refresh_after_git(self, msg):
        """記録・登録のあとに、版の一覧・選択肢・状態を更新する。"""
        self.revs = load_revisions()
        self.versions = {WORK: "WORKTREE"}
        for r in self.revs:
            if r.get("ref"):
                self.versions[f"{r['effective']} 施行（{r['ref']}）"] = r["ref"]
        vals = list(self.versions)
        for cb in (self.ver, self.c_old, self.c_new):
            cb["values"] = vals
        self.fill_revs()
        self.update_git_state()
        self.done(msg)

    def on_rev(self, _=None):
        sel = self.r_tree.selection()
        if sel:
            r = self.revs[int(sel[0])]
            text = "\n".join(r["notes"] + ["・" + c for c in r["changes"]])
            self.set_text(self.r_text, text)

    @staticmethod
    def open_path(path):
        try:
            import os
            os.startfile(str(path))                              # Windowsの既定のアプリで開く
        except Exception:                                       # noqa: BLE001
            pass


def log_error(text):
    """画面のないアプリでは、エラーが見えないので、ファイルに残す。"""
    try:
        d = ROOT / "out"
        d.mkdir(exist_ok=True)
        path = d / "gui-error.log"
        with open(path, "a", encoding="utf-8") as f:
            import datetime
            f.write(f"--- {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n{text}\n")
        return path
    except Exception:                                           # noqa: BLE001
        return None


def main():
    import faulthandler
    import traceback
    try:                                                        # 画面のないアプリが突然終わるときの記録（致命的なエラーも残す）
        (ROOT / "out").mkdir(exist_ok=True)
        faulthandler.enable(open(ROOT / "out" / "gui-crash.log", "a"))
    except Exception:                                           # noqa: BLE001
        pass
    if not (ROOT / "src").is_dir():
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror("起動できません",
                             f"条文のフォルダ src が見つかりません。\n\n探した場所: {ROOT}\n\n"
                             "exe は、プロジェクトのフォルダ（src と .git がある所）の中に置いたまま起動してください。")
        return
    try:
        app = App()
        # 画面の操作中のエラーも、記録して知らせる（アプリは落とさない）
        def report(exc, val, tb):
            text = "".join(traceback.format_exception(exc, val, tb))
            path = log_error(text)
            messagebox.showerror("エラーが起きました", f"{val}\n\n詳細: {path or text[-600:]}")
        app.report_callback_exception = report
        app.mainloop()
    except BaseException:                                       # noqa: BLE001
        text = traceback.format_exc()
        path = log_error(text)
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("起動できません", f"{text.strip().splitlines()[-1]}\n\n詳細: {path or text[-600:]}")
        except Exception:                                       # noqa: BLE001
            pass
        raise


if __name__ == "__main__":
    main()

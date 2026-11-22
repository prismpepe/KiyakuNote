"""Windows のGUI（Tkinter）。検索・条文の閲覧・整合性チェック・新旧対照表・Word出力・版の一覧。

起動: python -m kiyakunote gui  （または KiyakuNote.pyw をダブルクリック）
画面の操作はすべて、コマンドラインと同じ処理（kiyakunote の各モジュール）を呼ぶ。
"""
import re
import subprocess
import sys
import tempfile
import unicodedata
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .compare import KINDS, appendix_changes, bare_reference_notes, compare_doc, render_bare_notes, render_table
from .core import APPENDIX_KINDS, Heading
from .lint import lint
from .render import article_text, render_doc
from .search import build_index, doc_order, excerpt, find_spans, norm, plain, refs_of, search
from . import APP_DESCRIPTION, APP_NAME, __version__
from .versions import ROOT, load_revisions, load_version
from . import book, endmatter, gitops, mdedit, settings
from .gui_style import Styler

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
        self.title(f"{APP_NAME} {__version__}")
        self.geometry("1280x820")
        self.minsize(960, 620)
        self.cfg = settings.load()
        self.styler = Styler(self, self.cfg)                     # フォント・タブ・ボタンの見た目（設定で変えられる）
        self.configure(background="#f3f5f8")
        self.revs = load_revisions()
        self.versions = {WORK: "WORKTREE"}
        for r in self.revs:
            if r.get("ref"):
                self.versions[f"{r['effective']} 施行（{r['ref']}）"] = r["ref"]
        self.reg = None
        self.db = None
        self.tmp = Path(tempfile.mkdtemp(prefix="kiyakunote-gui-"))
        self.repo = ROOT
        self.undo = []                  # 保存前のファイル内容 [(パス, 内容)]。元に戻す用
        self.cmp_rows = []
        self.cmp_notes = []
        self.cmp_labels = ("", "")
        self.hl = None
        self.hl_iid = None
        self.status = tk.StringVar(value="")
        self._top()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.tab_read = self._tab_read()
        self.tab_search = self._tab_search()
        self.tab_lint = self._tab_lint()
        self.tab_cmp = self._tab_cmp()
        self.tab_out = self._tab_out()
        self.tab_rev = self._tab_rev()
        self.tab_hist = self._tab_hist()
        for t, name in ((self.tab_read, "条文"), (self.tab_search, "検索"), (self.tab_lint, "整合性チェック"),
                        (self.tab_cmp, "新旧対照表"), (self.tab_out, "Word出力"), (self.tab_rev, "版の一覧"),
                        (self.tab_hist, "変更履歴")):
            self.nb.add(t, text=f"  {name}  ")
        ttk.Label(self, textvariable=self.status, anchor="w", style="Status.TLabel").pack(fill="x", side="bottom")
        self.fill_revs()
        self.update_git_state()
        self.fill_hist()
        self.load_version()

    # ---- 共通 ----
    def busy(self, msg):
        self.status.set(msg)
        self.config(cursor="watch")
        self.update_idletasks()

    def done(self, msg=""):
        self.status.set(msg)
        self.config(cursor="")
        if hasattr(self, "btn_edit"):
            self.update_buttons()

    def _top(self):
        f = ttk.Frame(self)
        f.pack(fill="x", padx=6, pady=6)
        ttk.Label(f, text="表示する版:").pack(side="left")
        self.ver = ttk.Combobox(f, values=list(self.versions), state="readonly", width=42)
        self.ver.set(WORK)
        self.ver.pack(side="left", padx=4)
        self.ver.bind("<<ComboboxSelected>>", lambda e: self.load_version())
        ttk.Button(f, text="読み直す", command=self.load_version).pack(side="left", padx=4)
        ttk.Button(f, text="バージョン情報", command=self.about).pack(side="right", padx=2)
        ttk.Button(f, text="表示設定…", command=self.open_settings).pack(side="right", padx=2)
        ttk.Label(f, text=f"{APP_NAME}（KiyakuNote）  バージョン {__version__}", style="Hint.TLabel").pack(side="right", padx=8)

    def set_cfg(self, cfg, save=False):
        """表示設定を画面に反映する。save=True なら保存もする。"""
        self.cfg = settings.clean(cfg)
        self.styler.apply(self.cfg)
        self.show_docx_font()
        if save:
            settings.save(self.cfg)
            self.done("表示設定を保存しました")

    def open_settings(self):
        from .gui_settings import SettingsDialog
        SettingsDialog(self)

    def about(self):
        lines = [f"{APP_NAME}（KiyakuNote）", f"バージョン {__version__}", "", APP_DESCRIPTION, "",
                 "Copyright (c) 2026 prismpepe", "MIT License", "https://github.com/prismpepe/KiyakuNote"]
        messagebox.showinfo("バージョン情報", chr(10).join(lines))

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
        self.update_buttons()
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
        self.btn_md = ttk.Button(bar, text="Markdownエディタで開く…", command=self.open_md_editor)
        self.btn_md.pack(side="right", padx=2)
        self.btn_edit = ttk.Button(bar, text="編集…", width=18, command=self.do_edit)
        self.btn_edit.pack(side="left", padx=2)
        self.btn_new = ttk.Button(bar, text="新設…", width=18, command=self.do_new)
        self.btn_new.pack(side="left", padx=2)
        self.btn_del = ttk.Button(bar, text="削除…", width=18, command=self.do_delete)
        self.btn_del.pack(side="left", padx=2)
        self.btn_undo = ttk.Button(bar, text="直前の保存を元に戻す", command=self.undo_last)
        self.btn_undo.pack(side="left", padx=14)
        self.btn_hint = ttk.Label(bar, text="", style="Hint.TLabel")
        self.btn_hint.pack(side="left")
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
        self.body = self.styler.text_widget(right, "text", wrap="char", height=8, spacing1=3, spacing3=3)
        sb2 = ttk.Scrollbar(right, command=self.body_yview)
        self.body.configure(yscrollcommand=sb2.set, state="disabled")
        self.body.bind("<MouseWheel>", self.body_wheel)
        self.body.pack(side="top", fill="both", expand=True)
        ttk.Label(right, text="この条が参照している先／この条を参照している元").pack(anchor="w", pady=(6, 0))
        self.refs_box = self.styler.text_widget(right, "input", wrap="char", height=4, state="disabled")
        self.body.tag_configure("hit", background="#ffe14d", foreground="#000000")
        for lv, sp in (("h1", 12), ("h2", 10), ("h3", 8)):        # 文書名・章・条の見出し
            self.body.tag_configure(lv, font=self.styler.f_text_bold, foreground="#1f4e79", spacing1=sp, spacing3=2)
        self.refs_box.pack(side="top", fill="x")
        pw.add(left, weight=1)
        pw.add(right, weight=3)
        return f

    def body_wheel(self, e):
        """ホイールは、行でなくピクセル単位で動かす（表は高い1行として埋め込まれているので、行単位だと途中が飛ぶ）。"""
        self.body.yview_scroll(int(-e.delta / 120 * 60), "pixels")
        return "break"

    def body_yview(self, *a):
        if len(a) == 3 and a[0] == "scroll" and a[2] == "units":      # スクロールバーの矢印・クリックも同様
            self.body.yview_scroll(int(a[1]) * 40, "pixels")
        elif len(a) == 3 and a[0] == "scroll" and a[2] == "pages":
            self.body.yview_scroll(int(a[1]) * max(100, self.body.winfo_height() - 40), "pixels")
        else:
            self.body.yview(*a)

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
        if any(d.kind == "規約" for d in self.reg.docs.values()):          # 巻末: 改訂履歴・署名
            self.tree.insert("", "end", iid="@history", text=f"{endmatter.HISTORY_TITLE}（巻末）")
            if endmatter.load_okugaki(getattr(self.reg, "src_dir", ROOT / "src")):
                self.tree.insert("", "end", iid="@sign", text=f"{endmatter.SIGN_TITLE}（巻末）")

    def set_text(self, widget, text):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.config(state="disabled")

    def set_body(self, text):
        """条文の表示欄に出す。Markdownの見出し記号（# ###）は外して見出しの書式にし、段落の間の余分な空行は詰める。"""
        w = self.body
        w.config(state="normal")
        w.delete("1.0", "end")
        for ln in (x for x in text.split("\n") if x.strip()):             # 空行・空白だけの行は出さない
            m = re.match(r"^(#{1,6})[ ]*(.*)$", ln)
            if m:
                w.insert("end", m.group(2) + "\n", (f"h{min(len(m.group(1)), 3)}",))
            else:
                w.insert("end", ln + "\n")
        w.delete("end-2c", "end-1c")                 # 末尾の余分な改行
        w.config(state="disabled")

    def highlight_body(self):
        """検索から開いたときは、条文の中の検索語を黄色のマーカーで示す。"""
        w = self.body
        w.tag_remove("hit", "1.0", "end")
        sel = self.tree.selection()
        hl = self.hl if sel and sel[0] == self.hl_iid else None        # 検索から開いた条を表示している間だけ
        if not hl or not hl[0]:
            return
        raw = w.get("1.0", "end-1c")
        chars, idx = [], []                          # 表示の文字を、検索と同じ全角・半角をそろえた形にして、位置を対応づける
        for i, c in enumerate(raw):
            for ch in unicodedata.normalize("NFKC", c):
                chars.append(ch)
                idx.append(i)
        text = "".join(chars)
        try:
            if hl[1]:
                spans = find_spans(text, hl[0], True)
            else:
                spans = []
                for term in [x for x in norm(hl[0]).split(" ") if x]:
                    spans += [(m.start(), m.end()) for m in re.finditer(re.escape(term), text)]
        except ValueError:
            return
        spans = [(idx[a], idx[b - 1] + 1) for a, b in sorted(spans) if b > a]
        for a, b in spans:
            w.tag_add("hit", f"1.0+{a}c", f"1.0+{b}c")
        if spans:
            w.see(f"1.0+{spans[0][0]}c")

    def on_tree(self, _=None):
        self._on_tree()
        self.update_buttons()

    def _on_tree(self):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        if "|h|" in iid:
            return
        if iid in ("@history", "@sign"):
            self.show_endmatter(iid)
            return
        if "|" not in iid:
            d = self.reg.docs[iid]
            if d.kind in APPENDIX_KINDS:
                self.show_appendix(d)
            else:
                self.set_body(render_doc(self.reg, d))
                self.set_text(self.refs_box, "")
            return
        did, aid = iid.split("|", 1)
        d = self.reg.docs[did]
        art = next((a for a in d.articles if a.id == aid), None)
        if art is None:
            return
        self.set_body(article_text(self.reg, d, art))
        self.highlight_body()
        out, inc = refs_of(self.db, f"{did}#{aid}")
        lines = ["【参照している先】"] + [f"  {a} → {c}" for a, _, c in out] if out else ["【参照している先】  なし"]
        lines += ["【参照している元】"] + [f"  {self.reg.docs[x].title} {y} → {z}" for x, y, z in inc] if inc else ["【参照している元】  なし"]
        self.set_text(self.refs_box, "\n".join(lines))

    def show_appendix(self, d):
        """別表・別紙。HTMLの表は、罫線つきの表として出す（Markdownやタグのソースは見せない）。"""
        from .gui_table import parse_md_table, parse_table, plain_text, split_body, table_frame
        n = self.reg.appendix_no(d)
        label = "別図" if d.kind == "別図" else (f"別表第{n}" if d.kind == "別表" else f"{d.kind}{n}")
        w = self.body
        w.config(state="normal")
        w.delete("1.0", "end")
        w.insert("end", f"{label}　{d.title}\n", ("h2",))
        if d.meta.get("deleted") == "true":
            w.insert("end", "（削除）\n")
        elif "<tr" in d.raw_body or re.search(r"(?m)^\s*\|.*\|\s*$", d.raw_body):
            wheel = self.body_wheel
            for kind, chunk in split_body(d.raw_body):
                if kind in ("table", "mdtable"):
                    cells = parse_table(chunk) if kind == "table" else parse_md_table(chunk)
                    fr = table_frame(w, cells, self.styler.f_ui, self.styler.f_ui_bold, wheel)
                    w.window_create("end", window=fr, padx=2, pady=6)
                    w.insert("end", "\n")
                else:
                    s = plain_text(chunk)
                    if s.strip():
                        w.insert("end", s + "\n")
        else:
            self.insert_images(w, d.raw_body)
        w.config(state="disabled")
        self.set_text(self.refs_box, "")

    def insert_images(self, w, raw):
        """本文の ![](画像) を画像として、それ以外の行は文字として、表示欄に入れる。"""
        from . import appendix_edit as ae
        base = Path(getattr(self.reg, "src_dir", ROOT / "src"))
        self._imgs = []                                            # PhotoImage は持っていないと消えるので保持する
        width = max(400, w.winfo_width() - 40)
        for ln in raw.splitlines():
            m = ae.IMG.fullmatch(ln.strip())
            if not m:
                if ln.strip():
                    w.insert("end", ln + "\n")
                continue
            f = base / m.group(2)
            try:
                from PIL import Image, ImageTk
                im = Image.open(f)
                im.load()
                if im.width > width:
                    im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
                ph = ImageTk.PhotoImage(im)
            except Exception as e:                                  # noqa: BLE001
                w.insert("end", f"（画像を表示できません: {m.group(2)}　{e}）\n")
                continue
            self._imgs.append(ph)
            w.image_create("end", image=ph, padx=2, pady=6)
            w.insert("end", "\n")

    def show_endmatter(self, iid):
        """巻末の項目（改訂履歴・理事長の署名）を表示する。"""
        from .gui_table import table_frame
        w = self.body
        w.config(state="normal")
        w.delete("1.0", "end")
        if iid == "@history":
            w.insert("end", endmatter.HISTORY_TITLE + "\n", ("h2",))
            revs = endmatter.history_for(load_revisions(), self.versions[self.ver.get()])
            wheel = self.body_wheel
            fr = table_frame(w, endmatter.history_cells(revs), self.styler.f_ui, self.styler.f_ui_bold, wheel)
            w.window_create("end", window=fr, padx=2, pady=6)
            w.insert("end", "\n")
        else:
            w.insert("end", endmatter.SIGN_TITLE + "\n", ("h2",))
            for para in endmatter.load_okugaki(getattr(self.reg, "src_dir", ROOT / "src")):
                w.insert("end", para + "\n\n")
        w.config(state="disabled")
        self.set_text(self.refs_box, "")

    # ---- 編集 ----
    def selected_article(self):
        """ツリーで選んでいる条を (文書ID, Article) で返す。条でなければ (文書ID, None)。"""
        sel = self.tree.selection()
        if sel and sel[0].startswith("@"):
            return None, None
        if not sel or "|h|" in sel[0]:
            return (sel[0].split("|")[0] if sel else None), None
        if "|" not in sel[0]:
            return sel[0], None
        did, aid = sel[0].split("|", 1)
        return did, next((a for a in self.reg.docs[did].articles if a.id == aid), None)

    def selected_appendix(self):
        """左の一覧で選んでいる別表・別紙・別図の文書。選んでいなければ案内を出して None。"""
        sel = self.tree.selection()
        d = self.reg.docs.get(sel[0]) if sel and "|" not in sel[0] else None
        if d is None or d.kind not in APPENDIX_KINDS:
            messagebox.showinfo("別表・別紙・別図を選んでください", "左の一覧で、別表・別紙・別図（一覧の下のほう）を選んでください。")
            return None
        if d.meta.get("deleted") == "true":
            messagebox.showinfo("削除済み", "この別表・別紙・別図は削除されています。")
            return None
        return d

    def after_appendix(self, did, msg):
        self.load_version()
        found = lint(self.reg)
        e = sum(1 for f in found if f[0] == "E")
        if self.tree.exists(did):
            self.tree.selection_set(did)
            self.tree.see(did)
            self.on_tree()
        self.update_git_state()
        self.done(f"{msg}。整合性チェック: エラー {e} 件、警告 {len(found) - e} 件" + ("（「整合性チェック」タブで確認してください）" if e else ""))
        if e:
            self.do_lint()

    def edit_history(self):
        if self.can_edit():
            from .gui_appendix import HistoryEditDialog
            HistoryEditDialog(self)

    def edit_sign(self):
        if self.can_edit():
            from .gui_appendix import SignEditDialog
            SignEditDialog(self)

    def appendix_edit_table(self):
        if not self.can_edit():
            return
        d = self.selected_appendix()
        if d is None:
            return
        from .tables import list_tables
        if not list_tables(d.raw_body):
            messagebox.showinfo("表がありません", "この文書には表がありません（画像の別紙・別図は「画像を差し替え…」）。")
            return
        from .gui_appendix import TableEditDialog
        TableEditDialog(self, d)

    def appendix_replace_image(self):
        if not self.can_edit():
            return
        d = self.selected_appendix()
        if d is None:
            return
        from . import appendix_edit as ae
        imgs = ae.images_in(d.raw_body)
        if not imgs:
            messagebox.showinfo("画像がありません", "この文書には画像がありません（表は「表を編集…」）。")
            return
        index = 0
        if len(imgs) > 1:
            from tkinter import simpledialog
            n = simpledialog.askinteger("画像の選択", f"画像が {len(imgs)} 枚あります。何枚目を差し替えますか？", minvalue=1, maxvalue=len(imgs), parent=self)
            if not n:
                return
            index = n - 1
        p = filedialog.askopenfilename(title="新しい画像を選ぶ", filetypes=[("画像", "*.png *.jpg *.jpeg *.gif *.webp")])
        if not p:
            return
        path = Path(d.path)
        old = path.read_bytes()
        try:
            ae.replace_image(path, index, p)
        except ae.AppendixError as e:
            messagebox.showerror("差し替えられません", str(e))
            return
        self.undo.append((path, old))
        self.after_appendix(d.id, "画像を差し替えました（古い画像のファイルは assets に残しています）")

    def appendix_new(self):
        if not self.can_edit():
            return
        from .gui_appendix import NewAppendixDialog
        NewAppendixDialog(self)

    def appendix_delete(self):
        if not self.can_edit():
            return
        d = self.selected_appendix()
        if d is None:
            return
        n = self.reg.appendix_no(d)
        label = "別図" if d.kind == "別図" else (f"別表第{n}" if d.kind == "別表" else f"{d.kind}{n}")
        if not messagebox.askyesno("削除", f"{label}（{d.title}）を削除します。\n番号の枠とIDは残り、本文は空になります（番号は詰めません）。\n"
                                         "この別表・別紙を参照している箇所は、整合性チェックでエラーになります。\n\n続けますか？"):
            return
        from . import appendix_edit as ae
        path = Path(d.path)
        old = path.read_bytes()
        try:
            ae.delete_appendix(path)
        except ae.AppendixError as e:
            messagebox.showerror("削除できません", str(e))
            return
        self.undo.append((path, old))
        self.after_appendix(d.id, f"{label}を削除しました")

    def open_md_editor(self):
        """選んでいる項目のファイルを、外部の Markdown エディタで開く。保存されたら自動で読み直す。"""
        if not self.can_edit():
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Markdownエディタで開く", "左の一覧で、開く項目（文書・条・別表など）を選んでください。")
            return
        src_dir = getattr(self.reg, "src_dir", ROOT / "src")
        path = mdedit.file_for_node(sel[0], self.reg, src_dir)
        if path is None or not path.exists():
            messagebox.showinfo("Markdownエディタで開く", "この項目に対応するファイルがありません。")
            return
        editor = mdedit.resolve_editor(self.cfg["md_editor"])
        try:
            mdedit.open_file(path, editor)
        except OSError as e:
            messagebox.showerror("開けません", str(e))
            return
        self.watch = (path, path.stat().st_mtime, sel[0])
        self.done(f"{path.name} を{'Markdownエディタ' if editor else '既定のアプリ'}で開きました。保存すると自動で読み直します")
        if not getattr(self, "_polling", False):
            self._polling = True
            self.after(1500, self.poll_watch)

    def poll_watch(self):
        w = getattr(self, "watch", None)
        if not w:
            self._polling = False
            return
        path, mtime, iid = w
        try:
            now = path.stat().st_mtime
        except OSError:
            self.watch = None
            self._polling = False
            return
        if now != mtime:
            self.watch = (path, now, iid)
            self.load_version()
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.see(iid)
                self.on_tree()
            self.update_git_state()
            self.done(f"{path.name} の変更を読み込みました")
        self.after(1500, self.poll_watch)

    # ---- 編集・新設・削除ボタン（選んでいる項目に応じて働きを変える）----
    def context(self):
        """左の一覧で選んでいる項目の種類: article / heading / doc / appendix / history / sign / None。"""
        sel = self.tree.selection()
        if not sel:
            return {"kind": None}
        iid = sel[0]
        if iid == "@history":
            return {"kind": "history"}
        if iid == "@sign":
            return {"kind": "sign"}
        if "|h|" in iid:
            return {"kind": "heading", "doc": self.reg.docs.get(iid.split("|")[0])}
        if "|" in iid:
            did, art = self.selected_article()
            return {"kind": "article", "doc": self.reg.docs.get(did), "art": art}
        d = self.reg.docs.get(iid)
        if d is None:
            return {"kind": None}
        return {"kind": "appendix" if d.kind in APPENDIX_KINDS else "doc", "doc": d}

    def update_buttons(self):
        """選んでいる項目で、できる操作だけを有効にし、ボタンの名前も合わせる。できない操作はグレーにする。"""
        from .tables import list_tables
        work = self.versions[self.ver.get()] == "WORKTREE"
        c = self.context()
        k, d = c["kind"], c.get("doc")
        edit = new = dele = None                                   # (名前, 有効か)
        if k == "article":
            edit, new, dele = "条を編集…", "条を新設…", "条を削除…"
            dele_ok = c["art"] is not None and not c["art"].deleted
            states = (c["art"] is not None, True, dele_ok)
        elif k in ("heading", "doc"):
            edit, new, dele = "編集…", "条を新設…" if k == "heading" else "新設…", "削除…"
            states = (False, True, False)
        elif k == "appendix":
            deleted = d.meta.get("deleted") == "true"
            has_tbl = bool(list_tables(d.raw_body))
            has_img = "![" in d.raw_body
            edit = "表を編集…" if has_tbl else "画像を差し替え…" if has_img else "編集…"
            new, dele = "別表等を新設…", "別表等を削除…"
            states = (not deleted and (has_tbl or has_img), True, not deleted)
        elif k == "history":
            edit, new, dele = "改訂履歴を編集…", "新設…", "削除…"
            states = (True, False, False)
        elif k == "sign":
            edit, new, dele = "署名を編集…", "新設…", "削除…"
            states = (True, False, False)
        else:
            edit, new, dele = "編集…", "新設…", "削除…"
            states = (False, False, False)
        for btn, text, ok in zip((self.btn_edit, self.btn_new, self.btn_del), (edit, new, dele), states):
            btn.configure(text=text, state="normal" if work and ok else "disabled")
        self.btn_undo.configure(state="normal" if work and self.undo else "disabled")
        md_ok = work and k is not None and mdedit.file_for_node(self.tree.selection()[0], self.reg, getattr(self.reg, "src_dir", ROOT / "src")) is not None
        self.btn_md.configure(state="normal" if md_ok else "disabled")
        self.btn_hint.configure(text="" if work else "（編集できるのは「作業中の src/」のときだけ）")

    def do_edit(self):
        k = self.context()["kind"]
        if k == "article":
            self.edit_selected()
        elif k == "history":
            self.edit_history()
        elif k == "sign":
            self.edit_sign()
        elif k == "appendix":
            from .tables import list_tables
            d = self.context()["doc"]
            has_tbl, has_img = bool(list_tables(d.raw_body)), "![" in d.raw_body
            if has_tbl and has_img and messagebox.askyesno("編集", "この文書には表と画像があります。\n表を編集しますか？（「いいえ」で画像の差し替え）"):
                self.appendix_edit_table()
            elif has_tbl and not has_img:
                self.appendix_edit_table()
            else:
                self.appendix_replace_image()

    def do_new(self):
        k = self.context()["kind"]
        if k in ("article", "heading"):
            self.new_article()
        elif k == "appendix":
            self.appendix_new()
        elif k == "doc":
            m = tk.Menu(self, tearoff=0)                           # 文書を選んでいるときは、条か別表等かを選ぶ
            m.add_command(label="条を新設…", command=self.new_article)
            m.add_command(label="別表・別紙・別図を新設…", command=self.appendix_new)
            m.tk_popup(self.btn_new.winfo_rootx(), self.btn_new.winfo_rooty() + self.btn_new.winfo_height())

    def do_delete(self):
        k = self.context()["kind"]
        if k == "article":
            self.delete_selected()
        elif k == "appendix":
            self.appendix_delete()

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
        entry = self.undo.pop()
        pairs = entry if isinstance(entry, list) else [entry]
        for path, old in pairs:
            if old is None:                                      # 新設したファイルは消す
                Path(path).unlink(missing_ok=True)
            else:
                Path(path).write_bytes(old)
        self.load_version()
        self.done(f"元に戻しました: {Path(pairs[0][0]).name}")

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
        self.hl_iid = iid if self.hl else None
        self.tree.see(iid)
        self.on_tree()

    # ---- 検索 ----
    def _tab_search(self):
        f = ttk.Frame(self.nb)
        top = ttk.Frame(f)
        top.pack(fill="x", pady=6)
        ttk.Label(top, text="検索語（空白でAND）:").pack(side="left")
        self.s_q = ttk.Entry(top, width=30)
        self.s_q.pack(side="left", padx=4)
        self.s_q.bind("<Return>", lambda e: self.do_search())
        self.s_re = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="正規表現", variable=self.s_re).pack(side="left", padx=(6, 0))
        ttk.Label(top, text="文書:").pack(side="left", padx=(10, 0))
        self.s_doc = ttk.Combobox(top, state="readonly", width=26)
        self.s_doc.pack(side="left", padx=4)
        ttk.Button(top, text="検索", command=self.do_search, style="Accent.TButton").pack(side="left", padx=6)
        self.s_info = ttk.Label(f, text="", style="Hint.TLabel")
        self.s_info.pack(anchor="w", pady=(0, 4))
        # 結果は、一致した語を黄色のマーカーで示すため、Text に並べる（1件=見出し行＋抜粋行）
        box = ttk.Frame(f)
        box.pack(fill="both", expand=True)
        self.s_list = self.styler.text_widget(box, "text", wrap="char", state="disabled", cursor="arrow")
        sb = ttk.Scrollbar(box, command=self.s_list.yview)
        self.s_list.configure(yscrollcommand=sb.set)
        self.s_list.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.s_list.tag_configure("head", font=self.styler.f_ui_bold, foreground="#1f4e79", spacing1=8)
        self.s_list.tag_configure("hit", background="#ffe14d", foreground="#000000")        # 一致した語（黄色のマーカー）
        self.s_list.tag_configure("sel", background="#cfe3f8")
        self.s_list.tag_raise("hit")
        self.s_list.bind("<Button-1>", self.on_search_click)
        self.s_list.bind("<Double-1>", self.on_search_open)
        self.s_hits = []                    # [(文書ID, ノードID)]
        self.s_sel = None
        self.s_last = ("", False)
        return f

    def do_search(self):
        q = self.s_q.get().strip()
        if not q:
            return
        rx = self.s_re.get()
        doc = None
        if self.s_doc.get() != "（すべて）":
            doc = next((d.id for d in self.reg.docs.values() if d.title == self.s_doc.get()), None)
        try:
            rows = search(self.db, q, doc=doc, limit=300, regex=rx)
        except ValueError as e:
            self.s_info.config(text=str(e))
            return
        w = self.s_list
        w.config(state="normal")
        w.delete("1.0", "end")
        self.s_hits, self.s_sel, self.s_last = [], None, (q, rx)
        for i, (title, did, label, art_title, text, level, nid) in enumerate(rows):
            head = f"{title}　{label}" + (f"（{art_title}）" if level == "article" and art_title else "")
            w.insert("end", head + "\n", ("head", f"r{i}"))
            snip, spans = excerpt(text or art_title, q, 60, rx)
            start = w.index("end-1c")
            w.insert("end", snip + "\n", (f"r{i}",))
            for a, b in spans:
                w.tag_add("hit", f"{start}+{a}c", f"{start}+{b}c")
            self.s_hits.append((did, nid))
        w.config(state="disabled")
        self.s_info.config(text=f"{len(rows)}件" + ("（上限300）" if len(rows) >= 300 else "")
                           + "　一致した語は黄色で示します。クリックで選び、ダブルクリックで条文を開く")

    def _hit_at(self, event):
        idx = self.s_list.index(f"@{event.x},{event.y}")
        for tag in self.s_list.tag_names(idx):
            if tag.startswith("r") and tag[1:].isdigit():
                return int(tag[1:])
        return None

    def on_search_click(self, event):
        i = self._hit_at(event)
        self.s_list.tag_remove("sel", "1.0", "end")
        self.s_sel = i
        if i is not None:
            rng = self.s_list.tag_ranges(f"r{i}")
            if rng:
                self.s_list.tag_add("sel", rng[0], rng[-1])
                self.s_list.tag_raise("hit")
        return "break"

    def on_search_open(self, event=None):
        i = self._hit_at(event) if event is not None else self.s_sel
        if i is not None and 0 <= i < len(self.s_hits):
            self.hl = self.s_last                       # 開いた条文でも、検索語を黄色で示す
            self.goto(*self.s_hits[i])
        return "break"

    # ---- 整合性チェック ----
    def _tab_lint(self):
        f = ttk.Frame(self.nb)
        top = ttk.Frame(f)
        top.pack(fill="x", pady=6)
        ttk.Button(top, text="チェックを実行", command=self.do_lint, style="Accent.TButton").pack(side="left")
        self.l_info = ttk.Label(top, text="", style="Hint.TLabel")
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
        self.l_tree.tag_configure("E", foreground="#a00018")
        self.l_tree.tag_configure("W", foreground="#7a4a00")
        ttk.Label(f, text="E=エラー（直さないと出力できない）／W=警告（原文はそのままで、確認が必要）", style="Hint.TLabel").pack(anchor="w", pady=4)
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
        ttk.Button(top, text="対照表を作る", command=self.do_compare, style="Accent.TButton").pack(side="left", padx=8)
        top2 = ttk.Frame(f)
        top2.pack(fill="x")
        self.c_info = ttk.Label(top2, text="（作業中の src/ を編集したあと、「改正後」を作業中にして作ります）", style="Hint.TLabel")
        self.c_info.pack(side="left")
        ttk.Button(top2, text="Wordで保存", command=lambda: self.save_cmp("docx")).pack(side="right", padx=2)
        ttk.Button(top2, text="Markdownで保存", command=lambda: self.save_cmp("md")).pack(side="right", padx=2)
        pw = ttk.PanedWindow(f, orient="vertical")
        pw.pack(fill="both", expand=True, pady=4)
        cols = ("kind", "doc", "art")
        tree_box = ttk.Frame(pw)
        self.c_tree = ttk.Treeview(tree_box, columns=cols, show="headings", selectmode="browse", height=14)
        for c, t, w in (("kind", "区分", 130), ("doc", "文書", 300), ("art", "条", 500)):
            self.c_tree.heading(c, text=t)
            self.c_tree.column(c, width=w, anchor="w")
        c_sb = ttk.Scrollbar(tree_box, command=self.c_tree.yview)      # 行が多いとき、続きがあることが分かるようにする
        self.c_tree.configure(yscrollcommand=c_sb.set)
        self.c_tree.pack(side="left", fill="both", expand=True)
        c_sb.pack(side="left", fill="y")
        self.c_tree.bind("<<TreeviewSelect>>", self.on_cmp_select)
        pw.add(tree_box, weight=2)
        pair = ttk.Frame(pw)
        self.c_o = self._mk_text(pair, "改正前")
        self.c_n = self._mk_text(pair, "改正後")
        pw.add(pair, weight=2)
        return f

    def _mk_text(self, parent, title):
        fr = ttk.LabelFrame(parent, text=title)
        fr.pack(side="left", fill="both", expand=True, padx=2)
        t = self.styler.text_widget(fr, "text", wrap="char", state="disabled", height=8, width=10)
        sb = ttk.Scrollbar(fr, command=t.yview)
        t.configure(yscrollcommand=sb.set)
        t.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        # 削除は赤の取消線＋薄い赤の地、追加は濃い青の太字の下線＋薄い青の地（色だけに頼らず形でも区別できる）
        t.tag_configure("del", foreground="#a00018", background="#ffe1e1", overstrike=True)
        t.tag_configure("ins", foreground="#00306e", background="#d9ecff", underline=True, font=self.styler.f_text_bold)
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
        ndoc = len({r[1] for r in self.cmp_rows})
        if self.cmp_rows:
            s += f"（{ndoc}文書。一覧は下にスクロールできます）"
        extra = f"　別表・別紙 {len(self.cmp_ap)}件" if self.cmp_ap else ""
        warn = f"　／　要確認の直書き参照 {len(self.cmp_notes)}件（保存した対照表の末尾に載ります）" if self.cmp_notes else ""
        self.c_info.config(text=s + extra + warn, foreground="#111")
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
            self.apply_docx_font()
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
        ttk.Button(row, text="Wordで出力…", command=self.do_docx, style="Accent.TButton").pack(side="left", padx=10)
        row2 = ttk.Frame(box)
        row2.pack(fill="x", padx=10, pady=(0, 6))
        self.out_separate = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="「（すべて）」のとき、一冊にまとめず、文書ごとの個別のファイルで出力する", variable=self.out_separate).pack(side="left")
        row3 = ttk.Frame(box)
        row3.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Button(row3, text="冊子の構成を編集…", command=self.edit_book).pack(side="left")
        ttk.Label(row3, text="（「（すべて）」で一冊にまとめるときの、表紙・目次・中表紙・文書の順番）", style="Hint.TLabel").pack(side="left", padx=8)
        ttk.Label(box, text="番号は計算済み、参照は展開済み。別表・別紙・別図（画像を含む）と、規約の巻末の改訂履歴・署名が付きます。\n"
                            "「（すべて）」は、表紙・目次・中表紙（使用細則・細則・別表など）つきの一冊の管理規約になります（構成は「冊子の構成を編集…」）。\n"
                            "目次のページ番号は、Wordで開いたときに「フィールドを更新しますか」と聞かれるので「はい」を選ぶと入ります。\n"
                            "整合性チェックでエラーがあると出力できません。",
                  style="Hint.TLabel").pack(anchor="w", padx=10, pady=(0, 6))
        self.docx_info = ttk.Label(box, text="", style="Hint.TLabel")
        self.docx_info.pack(anchor="w", padx=10, pady=(0, 10))
        self.show_docx_font()
        return f

    def show_docx_font(self):
        c = self.cfg
        custom = c["docx_family"] or c["docx_size"]
        self.docx_info.config(text="Wordの書式: " + (f"{c['docx_family'] or 'MS 明朝'} {c['docx_size'] or 10.5}pt" if custom
                                                  else "従来どおり（MS 明朝 10.5pt）") + "　（右上の「表示設定…」で変えられます）")

    def apply_docx_font(self):
        from . import docx_out
        docx_out.configure(self.cfg["docx_family"], self.cfg["docx_size"])

    def do_docx(self):
        errors = [f for f in lint(self.reg) if f[0] == "E"]
        if errors:
            messagebox.showerror("出力できません", f"整合性チェックにエラーが {len(errors)} 件あります。先に直してください。")
            return
        which = self.out_doc.get()
        docs = [d for d in sorted(self.reg.docs.values(), key=doc_order)
                if d.kind not in APPENDIX_KINDS and (which == "（すべて）" or d.title == which)]
        src_dir = getattr(self.reg, "src_dir", ROOT / "src")
        whole = which == "（すべて）" and not self.out_separate.get()
        plan = None
        if whole:
            try:
                plan = self.book_plan()
            except book.BookError as e:
                messagebox.showerror("冊子の構成を読めません", str(e))
                return
            errs, notes = book.check_plan(self.reg, plan)
            if errs:
                messagebox.showerror("冊子の構成にエラーがあります", "\n".join(errs) + "\n\n「冊子の構成を編集…」で直してください。")
                return
            if notes and not messagebox.askyesno("冊子の構成の確認", "\n".join(notes) + "\n\nこのまま出力しますか？"):
                return
        folder = filedialog.askdirectory(title="出力先のフォルダ")
        if not folder:
            return
        from .docx_out import build_book, build_docx
        self.apply_docx_font()
        revs = endmatter.history_for(load_revisions(), self.versions[self.ver.get()])
        self.busy("Wordを出力中…")
        if whole:
            main = next((d for d in self.reg.docs.values() if d.kind == "規約"), None)
            path = Path(folder) / f"{main.title if main else '管理規約'}（全体）.docx"
            build_book(self.reg, plan, path, src_dir=src_dir, revisions=revs)
            self.done(f"一冊の管理規約を出力しました: {path}")
            self.open_path(folder)
            return
        for d in docs:
            build_docx(self.reg, d, Path(folder) / f"{d.title}.docx", src_dir=src_dir, revisions=revs)
        self.done(f"{len(docs)} 件を出力しました: {folder}")
        self.open_path(folder)

    def effective_label(self):
        """表示している版の施行日（「2026年6月1日」の形）。分からなければ空。"""
        ref = self.versions[self.ver.get()]
        revs = [r for r in load_revisions() if r.get("effective")]
        me = next((r for r in revs if r.get("ref") == ref), None) if ref != "WORKTREE" else max(
            (r for r in revs if r.get("ref")), key=lambda r: r["effective"], default=None)
        if not me:
            return ""
        y, m, d = me["effective"].split("-")
        return f"{int(y)}年{int(m)}月{int(d)}日"

    def book_plan(self):
        """冊子の構成。src/book.txt があればそれ、無ければ既定。"""
        return book.plan_for(self.reg, getattr(self.reg, "src_dir", ROOT / "src"), self.effective_label())

    def edit_book(self):
        from .gui_appendix import BookEditDialog
        BookEditDialog(self)

    # ---- 版の一覧 ----
    def _tab_rev(self):
        f = ttk.Frame(self.nb)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(6, 0))
        ttk.Button(bar, text="変更を記録…", command=self.record_changes).pack(side="left", padx=2)
        ttk.Button(bar, text="新しい版として登録…", command=self.register_version).pack(side="left", padx=2)
        self.git_state = ttk.Label(bar, text="", style="Hint.TLabel")
        self.git_state.pack(side="left", padx=12)
        cols = ("res", "eff", "ref", "n")
        self.r_tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse", height=12)
        for c, t, w in (("res", "総会決議日", 110), ("eff", "施行日", 110), ("ref", "条文を持つ版", 200), ("n", "改定件数", 80)):
            self.r_tree.heading(c, text=t)
            self.r_tree.column(c, width=w, anchor="w")
        self.r_tree.pack(fill="x", pady=6)
        self.r_tree.bind("<<TreeviewSelect>>", self.on_rev)
        self.r_text = self.styler.text_widget(f, "input", wrap="char", state="disabled", height=14)
        self.r_text.pack(fill="both", expand=True)
        ttk.Label(f, text="条文を持つ版は、「表示する版」や新旧対照表で選べます。記録のみの版は、その時点の規約を取り込むと選べるようになります。",
                  style="Hint.TLabel").pack(anchor="w", pady=4)
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
        self.fill_hist()
        self.done(msg)

    def on_rev(self, _=None):
        sel = self.r_tree.selection()
        if sel:
            r = self.revs[int(sel[0])]
            text = "\n".join(r["notes"] + ["・" + c for c in r["changes"]])
            self.set_text(self.r_text, text)

    # ---- 変更履歴（git のコマンドを使わずに、履歴の確認・戻す・破棄・利用者名の設定ができる） ----
    def _tab_hist(self):
        f = ttk.Frame(self.nb)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(6, 2))
        ttk.Button(bar, text="いまの変更を見る", command=self.hist_show_now).pack(side="left", padx=2)
        ttk.Button(bar, text="この記録の変更を見る", command=self.hist_show_selected).pack(side="left", padx=2)
        ttk.Button(bar, text="この記録の状態に戻す…", command=self.hist_restore).pack(side="left", padx=2)
        ttk.Button(bar, text="未記録の変更を破棄…", command=self.hist_discard).pack(side="left", padx=2)
        ttk.Button(bar, text="利用者名の設定…", command=self.hist_user).pack(side="right", padx=2)
        ttk.Button(bar, text="更新", command=self.fill_hist).pack(side="right", padx=2)
        self.h_info = ttk.Label(f, text="", style="Hint.TLabel")
        self.h_info.pack(anchor="w", pady=2)
        pw = ttk.PanedWindow(f, orient="vertical")
        pw.pack(fill="both", expand=True, pady=4)
        box = ttk.Frame(pw)
        cols = ("date", "id", "msg", "tag")
        self.h_tree = ttk.Treeview(box, columns=cols, show="headings", selectmode="browse", height=10)
        for c, t_, w in (("date", "日時", 150), ("id", "記録ID", 90), ("msg", "説明", 600), ("tag", "版（タグ）", 200)):
            self.h_tree.heading(c, text=t_)
            self.h_tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(box, command=self.h_tree.yview)
        self.h_tree.configure(yscrollcommand=sb.set)
        self.h_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.h_tree.bind("<<TreeviewSelect>>", lambda e: self.hist_show_selected())
        pw.add(box, weight=1)
        fr = ttk.Frame(pw)
        self.h_text = self.styler.text_widget(fr, "input", wrap="none", state="disabled", height=12)
        hs = ttk.Scrollbar(fr, command=self.h_text.yview)
        self.h_text.configure(yscrollcommand=hs.set)
        self.h_text.pack(side="left", fill="both", expand=True)
        hs.pack(side="left", fill="y")
        self.h_text.tag_configure("add", foreground="#004d1a", background="#dcf5e0")
        self.h_text.tag_configure("del", foreground="#a00018", background="#ffe1e1")
        self.h_text.tag_configure("hunk", foreground="#00306e", background="#d9ecff")
        pw.add(fr, weight=2)
        self.h_rows = []
        return f

    def fill_hist(self):
        self.h_tree.delete(*self.h_tree.get_children())
        self.h_rows = []
        try:
            if not gitops.is_repo(self.repo):
                raise gitops.GitError("このフォルダは git の管理下にありません")
            self.h_rows = gitops.log(self.repo)
            n = len(gitops.changed_files(self.repo))
        except gitops.GitError as e:
            self.h_info.config(text=f"履歴を読めません: {e}")
            return
        for i, r in enumerate(self.h_rows):
            self.h_tree.insert("", "end", iid=str(i), values=(r["date"], r["id"], r["message"], "、".join(r["tags"])))
        self.h_info.config(text=f"記録 {len(self.h_rows)} 件（新しい順）。未記録の変更: {n} 件。"
                                "記録を選ぶと、その記録で変わった内容が下に出ます（緑=追加、赤=削除）。")

    def put_diff(self, text):
        w = self.h_text
        w.config(state="normal")
        w.delete("1.0", "end")
        for ln in text.splitlines():
            tag = "add" if ln.startswith("+") and not ln.startswith("+++") else "del" if ln.startswith("-") and not ln.startswith("---") \
                else "hunk" if ln.startswith("@@") else None
            w.insert("end", ln + "\n", tag)
        w.config(state="disabled")

    def hist_show_now(self):
        self.h_tree.selection_remove(*self.h_tree.selection())
        try:
            text = gitops.diff_text(self.repo)
        except gitops.GitError as e:
            messagebox.showerror("見られません", str(e))
            return
        self.put_diff(text or "未記録の変更はありません。")

    def hist_show_selected(self):
        sel = self.h_tree.selection()
        if not sel:
            return
        try:
            self.put_diff(gitops.diff_text(self.repo, self.h_rows[int(sel[0])]["id"]))
        except gitops.GitError as e:
            messagebox.showerror("見られません", str(e))

    def hist_restore(self):
        sel = self.h_tree.selection()
        if not sel:
            messagebox.showinfo("記録を選んでください", "上の一覧で、戻したい時点の記録を選んでください。")
            return
        r = self.h_rows[int(sel[0])]
        if not messagebox.askyesno("この記録の状態に戻す",
                                   f"条文（src/）を、{r['date']} の記録「{r['message']}」の状態にします。\n\n"
                                   "戻した内容は『未記録の変更』になります（記録の履歴は消えません）。\n"
                                   "よければ、そのあと「変更を記録」で記録してください。続けますか？"):
            return
        try:
            gitops.restore_to(self.repo, r["id"])
        except gitops.GitError as e:
            messagebox.showerror("戻せません", str(e))
            return
        self.refresh_after_git(f"{r['date']} の状態に戻しました。必要なら「変更を記録」してください")
        self.fill_hist()
        self.load_version()

    def hist_discard(self):
        try:
            files = gitops.changed_files(self.repo)
        except gitops.GitError as e:
            messagebox.showerror("できません", str(e))
            return
        if not files:
            messagebox.showinfo("未記録の変更を破棄", "未記録の変更はありません。")
            return
        names = "\n".join(f"  {st} {p}" for st, p in files[:12]) + ("\n  …" if len(files) > 12 else "")
        if not messagebox.askyesno("未記録の変更を破棄",
                                   f"未記録の変更 {len(files)} 件を捨てて、最後に記録した状態に戻します。\n\n{names}\n\n"
                                   "**この操作は元に戻せません。** 続けますか？", icon="warning"):
            return
        try:
            gitops.discard_changes(self.repo)
        except gitops.GitError as e:
            messagebox.showerror("できません", str(e))
            return
        self.refresh_after_git("未記録の変更を破棄しました")
        self.fill_hist()
        self.load_version()

    def hist_user(self):
        from .gui_git import UserDialog
        UserDialog(self)

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

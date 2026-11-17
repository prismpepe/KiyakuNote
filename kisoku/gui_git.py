"""GUIの、変更の記録（git）と版の登録のダイアログ。処理本体は kisoku.gitops。"""
import tkinter as tk
from tkinter import messagebox, ttk

from . import gitops


class CommitDialog(tk.Toplevel):
    """未記録の変更を一覧し、説明をつけて記録（git のコミット）する。"""

    def __init__(self, app, files):
        super().__init__(app)
        self.app = app
        self.title("変更を記録")
        self.geometry("640x420")
        self.transient(app)
        ttk.Label(self, text=f"未記録の変更 {len(files)} 件（M=変更、A/?=追加、D=削除）:").pack(anchor="w", padx=10, pady=(10, 2))
        box = tk.Listbox(self, height=10)
        for st, p in files:
            box.insert("end", f"{st:2} {p}")
        box.pack(fill="both", expand=True, padx=10)
        ttk.Label(self, text="記録の説明（何を変えたか）:").pack(anchor="w", padx=10, pady=(8, 0))
        self.msg = ttk.Entry(self)
        self.msg.insert(0, "条文の変更")
        self.msg.pack(fill="x", padx=10)
        self.msg.focus_set()
        bt = ttk.Frame(self)
        bt.pack(fill="x", padx=10, pady=10)
        ttk.Button(bt, text="記録する", command=self.ok).pack(side="right")
        ttk.Button(bt, text="キャンセル", command=self.destroy).pack(side="right", padx=6)

    def ok(self):
        try:
            cid = gitops.commit(self.app.repo, self.msg.get())
        except gitops.GitError as e:
            messagebox.showerror("記録できません", str(e), parent=self)
            return
        self.destroy()
        self.app.refresh_after_git(f"記録しました（{cid}）")


class RegisterDialog(tk.Toplevel):
    """施行日の版として登録する（タグ付け＋revisions.yaml）。"""

    def __init__(self, app, suggestion):
        super().__init__(app)
        self.app = app
        self.title("新しい版として登録")
        self.geometry("640x560")
        self.transient(app)
        f = ttk.Frame(self)
        f.pack(fill="x", padx=10, pady=10)
        self.res, self.eff, self.tag = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.tag_touched = False
        rows = (("総会決議日（例 2030-04-21）:", self.res), ("施行日（例 2030-06-01）:", self.eff), ("タグ名（git）:", self.tag))
        for r, (label, var) in enumerate(rows):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", pady=2)
            e = ttk.Entry(f, textvariable=var, width=24)
            e.grid(row=r, column=1, sticky="w", padx=6)
            if var is self.tag:
                e.bind("<Key>", lambda ev: setattr(self, "tag_touched", True))
        # 施行日を入れると、タグ名の案（v施行日）が入る。タグ名を自分で触ったあとは変えない
        self.eff.trace_add("write", lambda *_: None if self.tag_touched else self.tag.set(
            "v" + self.eff.get().strip() if self.eff.get().strip() else ""))
        ttk.Label(f, text="備考（任意）:").grid(row=3, column=0, sticky="w", pady=2)
        self.note = ttk.Entry(f, width=50)
        self.note.grid(row=3, column=1, sticky="w", padx=6)
        ttk.Label(self, text="改定内容（1行に1件。2つの版の差から作った下書きです。直せます）:").pack(anchor="w", padx=10)
        self.chg = tk.Text(self, height=12, wrap="char")
        self.chg.insert("1.0", "\n".join(suggestion))
        self.chg.pack(fill="both", expand=True, padx=10, pady=4)
        ttk.Label(self, text="登録すると、いまの内容にタグを付け、改訂履歴（revisions.yaml）に版を加えて記録します。\n"
                             "この版は、「表示する版」や新旧対照表で選べるようになります。", foreground="#555").pack(anchor="w", padx=10)
        bt = ttk.Frame(self)
        bt.pack(fill="x", padx=10, pady=10)
        ttk.Button(bt, text="登録する", command=self.ok).pack(side="right")
        ttk.Button(bt, text="キャンセル", command=self.destroy).pack(side="right", padx=6)

    def ok(self):
        repo = self.app.repo
        res, eff, tag = self.res.get().strip(), self.eff.get().strip(), self.tag.get().strip()
        errors = gitops.validate_revision(repo, res, eff, tag)
        if errors:
            messagebox.showerror("入力を確かめてください", "\n".join(errors), parent=self)
            return
        try:
            if gitops.changed_files(repo):
                if not messagebox.askyesno("未記録の変更", "src/ に未記録の変更があります。先に記録してから登録します。よろしいですか？",
                                           parent=self):
                    return
                gitops.commit(repo, f"改正の確定（{eff} 施行）")
            gitops.register_revision(repo, res, eff, tag, self.chg.get("1.0", "end").splitlines(), self.note.get())
        except gitops.GitError as e:
            messagebox.showerror("登録できません", str(e), parent=self)
            return
        self.destroy()
        self.app.refresh_after_git(f"{eff} 施行の版を登録しました（{tag}）")

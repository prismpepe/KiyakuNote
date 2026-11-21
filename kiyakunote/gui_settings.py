"""表示設定（フォントの種類・大きさ）のダイアログ。変更はすぐ画面に反映され、利用者ごとに保存される。"""
import tkinter as tk
from tkinter import messagebox, ttk

from . import settings
from .gui_style import family_choices, place_dialog

SAMPLE_UI = "条文　検索　新旧対照表　［変更を記録］　ナビゲーション・ボタン・説明の文字"
SAMPLE_TEXT = "第1条　この規約は、区分所有者の共同の利益を増進し、良好な住環境を確保することを目的とする。"
SAMPLE_INPUT = "1. {#art-001-p1} 入力欄・編集フォームの文字 ABC abc 123"


class SettingsDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("表示設定")
        self.transient(app)
        place_dialog(self, app)
        self.resizable(False, False)
        cfg = app.cfg
        fams = family_choices(self)
        self.vars = {}
        f = ttk.Frame(self, padding=10)
        f.pack(fill="both", expand=True)
        groups = (
            ("ナビゲーション（タブ・ボタン・メニュー・説明・一覧）", "ui", SAMPLE_UI),
            ("条文・新旧対照表の表示欄", "text", SAMPLE_TEXT),
            ("入力欄・編集フォーム", "input", SAMPLE_INPUT),
        )
        self.samples = {}
        for r, (title, key, sample) in enumerate(groups):
            box = ttk.LabelFrame(f, text=title, padding=8)
            box.grid(row=r, column=0, sticky="ew", pady=5)
            ttk.Label(box, text="フォント:").grid(row=0, column=0, sticky="w")
            fv = tk.StringVar(value=cfg[f"{key}_family"])
            cb = ttk.Combobox(box, textvariable=fv, values=fams, width=28)
            cb.grid(row=0, column=1, padx=6, sticky="w")
            ttk.Label(box, text="大きさ:").grid(row=0, column=2, padx=(10, 0))
            lo, hi = settings.LIMITS[f"{key}_size"]
            sv = tk.IntVar(value=cfg[f"{key}_size"])
            ttk.Spinbox(box, from_=lo, to=hi, textvariable=sv, width=5, command=self.preview).grid(row=0, column=3, padx=6)
            ttk.Label(box, text="pt").grid(row=0, column=4)
            lab = ttk.Label(box, text=sample, wraplength=620)
            lab.grid(row=1, column=0, columnspan=5, sticky="w", pady=(8, 0))
            self.vars[f"{key}_family"], self.vars[f"{key}_size"] = fv, sv
            self.samples[key] = lab
            cb.bind("<<ComboboxSelected>>", lambda e: self.preview())
            cb.bind("<FocusOut>", lambda e: self.preview())
        box = ttk.LabelFrame(f, text="Word出力の書式（任意。空・0 は従来どおり MS 明朝 10.5pt）", padding=8)
        box.grid(row=3, column=0, sticky="ew", pady=5)
        ttk.Label(box, text="フォント:").grid(row=0, column=0, sticky="w")
        dv = tk.StringVar(value=cfg["docx_family"])
        ttk.Combobox(box, textvariable=dv, values=[""] + fams, width=28).grid(row=0, column=1, padx=6, sticky="w")
        ttk.Label(box, text="大きさ:").grid(row=0, column=2, padx=(10, 0))
        ds = tk.DoubleVar(value=cfg["docx_size"])
        ttk.Spinbox(box, from_=0, to=24, increment=0.5, textvariable=ds, width=5).grid(row=0, column=3, padx=6)
        ttk.Label(box, text="pt").grid(row=0, column=4)
        ttk.Label(box, text="本文の書体と大きさを変えます。見出しの相対的な大きさや表の幅は変わりません。\n"
                            "Wordに入っているフォント名を入れてください（例: MS 明朝、游明朝、メイリオ）。",
                  style="Hint.TLabel").grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))
        self.vars["docx_family"], self.vars["docx_size"] = dv, ds
        bt = ttk.Frame(f)
        bt.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(bt, text="保存して閉じる", command=self.ok, style="Accent.TButton").pack(side="right")
        ttk.Button(bt, text="適用", command=self.apply).pack(side="right", padx=6)
        ttk.Button(bt, text="標準に戻す", command=self.reset).pack(side="left")
        ttk.Button(bt, text="キャンセル", command=self.cancel).pack(side="right", padx=6)
        self.before = dict(app.cfg)
        self.preview()
        self.grab_set()

    def values(self):
        d = {}
        for k, v in self.vars.items():
            try:
                d[k] = v.get()
            except tk.TclError:                      # 入力途中（空の数値など）
                d[k] = settings.DEFAULTS[k]
        return settings.clean(d)

    def preview(self):
        """見本の文字に、いまの選択を当てる（画面全体には「適用」で反映）。"""
        c = self.values()
        from tkinter import font as tkfont
        for key, lab in self.samples.items():
            lab.configure(font=tkfont.Font(family=c[f"{key}_family"], size=c[f"{key}_size"]))

    def apply(self):
        self.app.set_cfg(self.values(), save=False)

    def ok(self):
        try:
            self.app.set_cfg(self.values(), save=True)
        except OSError as e:
            messagebox.showerror("保存できません", str(e), parent=self)
            return
        self.destroy()

    def cancel(self):
        self.app.set_cfg(self.before, save=False)
        self.destroy()

    def reset(self):
        for k, v in settings.DEFAULTS.items():
            self.vars[k].set(v)
        self.preview()

"""別表・別紙の表を、画面に罫線つきの表として出す。解析は tables.py。"""
import tkinter as tk

from .tables import parse_md_table, parse_table, plain_text, split_body  # noqa: F401  （画面から使う）


def table_frame(parent, cells, font, bold_font, on_wheel=None, width=880):
    """罫線のある表（Frame）を作る。1行目などの見出しは太字・色付き。"""
    ncols = max((c + cs for _, c, _, cs, _, _ in cells), default=1)
    wrap = max(70, min(300, width // ncols - 24))              # 列が多い表は、1列を狭くして画面の幅に収める
    fr = tk.Frame(parent, background="#8a8a8a", padx=1, pady=1)          # 外枠の左・上の線
    for r, c, rs, cs, text, th in cells:
        lab = tk.Label(fr, text=text, font=bold_font if th else font, background="#dbe5f1" if th else "#ffffff",
                       foreground="#111111", justify="left" if not th else "center", anchor="nw" if not th else "n",
                       wraplength=wrap, padx=8, pady=4)
        lab.grid(row=r, column=c, rowspan=rs, columnspan=cs, sticky="nsew", padx=(0, 1), pady=(0, 1))
        if on_wheel:
            lab.bind("<MouseWheel>", on_wheel)
    if on_wheel:
        fr.bind("<MouseWheel>", on_wheel)
    return fr

"""別表・別紙の表を、画面に罫線つきの表として出す。解析は tables.py。"""
import tkinter as tk
from tkinter import font as tkfont

from .tables import parse_md_table, parse_table, plain_text, split_body  # noqa: F401  （画面から使う）

PAD_X = 8                      # セルの左右の余白
MIN_COL, MAX_COL = 60, 520     # 1列の文字部分の幅の下限・上限（画素）


def column_widths(cells, font, bold_font, available):
    """各列の、折り返しの幅（画素）。文字が収まる幅を基本に、画面の幅に収まらなければ比例して縮める。"""
    f, fb = tkfont.Font(font=font), tkfont.Font(font=bold_font)
    ncols = max((c + cs for _, c, _, cs, _, _ in cells), default=1)
    want = [MIN_COL] * ncols
    for _, c, _, cs, text, th in cells:
        if cs != 1:
            continue                                            # 結合セルは、列の幅を決めない
        ff = fb if th else f
        w = max((ff.measure(line) for line in text.split("\n")), default=0) + 4
        want[c] = max(want[c], min(MAX_COL, w))
    spare = available - ncols * (2 * PAD_X + 1) - 4             # 余白と罫線を除いた、文字部分に使える幅
    if sum(want) > spare > 0:                                   # 収まらないときは、いちばん広い列から順に狭める（短い列は折り返さない）
        lo, hi = MIN_COL // 2, max(want)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if sum(min(w, mid) for w in want) <= spare:
                lo = mid
            else:
                hi = mid - 1
        want = [min(w, lo) for w in want]
    return want


def table_frame(parent, cells, font, bold_font, on_wheel=None, width=880):
    """罫線のある表（Frame）を作る。1行目などの見出しは太字・色付き。width は、使える画面の幅（画素）。"""
    cols = column_widths(cells, font, bold_font, width)
    fr = tk.Frame(parent, background="#8a8a8a", padx=1, pady=1)          # 外枠の左・上の線
    for r, c, rs, cs, text, th in cells:
        wrap = sum(cols[c:c + cs]) + (cs - 1) * (2 * PAD_X + 1)
        lab = tk.Label(fr, text=text, font=bold_font if th else font, background="#dbe5f1" if th else "#ffffff",
                       foreground="#111111", justify="left" if not th else "center", anchor="nw" if not th else "n",
                       wraplength=max(MIN_COL // 2, wrap), padx=PAD_X, pady=4)
        lab.grid(row=r, column=c, rowspan=rs, columnspan=cs, sticky="nsew", padx=(0, 1), pady=(0, 1))
        if on_wheel:
            lab.bind("<MouseWheel>", on_wheel)
    if on_wheel:
        fr.bind("<MouseWheel>", on_wheel)
    return fr

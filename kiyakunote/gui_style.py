"""GUIの見た目: フォント（種類・大きさを設定で変えられる）、タブ・ボタン・一覧の色と大きさ。

文字の大きさは、名前つきフォント（KN_UI など）を各部品が共有するので、設定を変えると全体にすぐ反映される。
"""
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from . import settings

NAVY = "#1f4e79"
GO = "#2e7d32"
TAB_OFF = "#d6e0ec"
TAB_HOVER = "#b9cde4"
BTN = "#e4ecf6"
BTN_HOVER = "#c9dcf1"
INK = "#111111"
HINT = "#333333"
PAPER = "#ffffff"

PREFERRED = ("Yu Gothic UI", "Meiryo UI", "Meiryo", "Yu Gothic", "BIZ UDPGothic", "BIZ UDGothic", "MS UI Gothic",
             "Yu Mincho", "BIZ UDPMincho", "BIZ UDMincho", "MS PMincho", "MS Mincho", "MS 明朝", "MS Gothic", "MS ゴシック")


def family_choices(root):
    """候補のフォント名（日本語の主なものを先頭に、残りを五十音・ABC順に）。"""
    have = set(tkfont.families(root))
    first = [f for f in PREFERRED if f in have]
    rest = sorted(f for f in have if f not in first and not f.startswith("@"))
    return first + rest


class Styler:
    def __init__(self, root, cfg=None):
        self.root = root
        self.cfg = cfg or settings.load()
        self.style = ttk.Style(root)
        try:
            self.style.theme_use("clam")                 # 色・余白を指定しやすいテーマ
        except tk.TclError:
            pass
        self.f_ui = tkfont.Font(root, name="KN_UI")
        self.f_ui_bold = tkfont.Font(root, name="KN_UI_BOLD")
        self.f_tab = tkfont.Font(root, name="KN_TAB")
        self.f_tab_sel = tkfont.Font(root, name="KN_TAB_SEL")
        self.f_text = tkfont.Font(root, name="KN_TEXT")
        self.f_text_bold = tkfont.Font(root, name="KN_TEXT_BOLD")
        self.f_input = tkfont.Font(root, name="KN_INPUT")
        self.apply(self.cfg)

    def apply(self, cfg):
        self.cfg = settings.clean(cfg)
        c = self.cfg
        ui, tx, inp = c["ui_family"], c["text_family"], c["input_family"]
        us, ts, isz = c["ui_size"], c["text_size"], c["input_size"]
        self.f_ui.configure(family=ui, size=us)
        self.f_ui_bold.configure(family=ui, size=us, weight="bold")
        self.f_tab.configure(family=ui, size=us + 1)
        self.f_tab_sel.configure(family=ui, size=us + 1, weight="bold")
        self.f_text.configure(family=tx, size=ts)
        self.f_text_bold.configure(family=tx, size=ts, weight="bold")
        self.f_input.configure(family=inp, size=isz)
        for name in ("TkDefaultFont", "TkMenuFont", "TkTextFont", "TkHeadingFont", "TkCaptionFont", "TkTooltipFont"):
            try:
                tkfont.nametofont(name).configure(family=ui, size=us)
            except tk.TclError:
                pass
        try:
            tkfont.nametofont("TkFixedFont").configure(family=inp, size=isz)
        except tk.TclError:
            pass
        st = self.style
        row = max(22, int(us * 2.0))
        st.configure(".", font=self.f_ui, background="#f3f5f8", foreground=INK)
        st.configure("TFrame", background="#f3f5f8")
        st.configure("TLabel", background="#f3f5f8", foreground=INK, font=self.f_ui)
        st.configure("TLabelframe", background="#f3f5f8")
        st.configure("TLabelframe.Label", background="#f3f5f8", foreground=NAVY, font=self.f_ui_bold)
        # タブ: 大きく、選択中は濃い色と太字で区別する
        st.configure("TNotebook", background="#f3f5f8", borderwidth=0, tabmargins=(4, 6, 4, 0))
        st.configure("TNotebook.Tab", font=self.f_tab, padding=(16, 6), background=TAB_OFF, foreground=INK,
                     borderwidth=1)
        st.map("TNotebook.Tab",
               background=[("selected", NAVY), ("active", TAB_HOVER)],
               foreground=[("selected", "#ffffff"), ("active", INK)],
               font=[("selected", self.f_tab_sel)],
               padding=[("selected", (16, 6))],           # 選択中も同じ大きさ（高さ・余白をそろえる）
               expand=[("selected", (0, 0, 0, 0))])
        # ボタン: 大きく、枠と色をつける。主な操作は「Accent」
        st.configure("TButton", font=self.f_ui_bold, padding=(10, 4), background=BTN, foreground=INK, borderwidth=1,
                     relief="raised")
        st.map("TButton", background=[("pressed", "#a9c4e4"), ("active", BTN_HOVER), ("disabled", "#e8e8e8")],
               foreground=[("disabled", "#888888")])
        st.configure("Accent.TButton", font=self.f_ui_bold, padding=(10, 4), background=GO, foreground="#ffffff")       # 実行ボタン（タブの選択色と違う色）
        st.map("Accent.TButton", background=[("pressed", "#1b4d1f"), ("active", "#3d8c43")],
               foreground=[("disabled", "#cccccc"), ("!disabled", "#ffffff")])
        st.configure("TEntry", font=self.f_input, padding=3, fieldbackground=PAPER)
        st.configure("TCombobox", font=self.f_input, padding=3, fieldbackground=PAPER)
        st.configure("TSpinbox", font=self.f_input, padding=4, fieldbackground=PAPER)
        self.root.option_add("*TCombobox*Listbox.font", self.f_input)
        self.root.option_add("*Listbox.font", self.f_input)
        self.root.option_add("*Font", self.f_ui)
        st.configure("Treeview", font=self.f_ui, rowheight=row, background=PAPER, fieldbackground=PAPER,
                     foreground=INK)
        st.configure("Treeview.Heading", font=self.f_ui_bold, padding=(6, 3), background="#dbe5f1", foreground=INK)
        st.map("Treeview", background=[("selected", NAVY)], foreground=[("selected", "#ffffff")])
        st.configure("Hint.TLabel", foreground=HINT, background="#f3f5f8", font=self.f_ui)
        st.configure("Status.TLabel", background="#e1e8f0", foreground=INK, font=self.f_ui, padding=(8, 4))

    def text_widget(self, parent, kind="text", **kw):
        """条文・入力用の tk.Text（濃い文字・白い背景・行間つき）。"""
        font = self.f_text if kind == "text" else self.f_input
        opts = dict(font=font, foreground=INK, background=PAPER, insertbackground=INK, selectbackground=NAVY,
                    selectforeground="#ffffff", padx=10, pady=8, spacing1=2, spacing3=3, relief="solid",
                    borderwidth=1, highlightthickness=0)
        opts.update(kw)
        return tk.Text(parent, **opts)


def center_on(win, parent):
    """ダイアログを、親ウインドウの真ん中に出す（画面の左上に出ないように）。"""
    win.update_idletasks()
    w = win.winfo_width() if win.winfo_width() > 1 else win.winfo_reqwidth()
    h = win.winfo_height() if win.winfo_height() > 1 else win.winfo_reqheight()
    parent.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    x = max(0, min(x, win.winfo_screenwidth() - w))
    y = max(0, min(y, win.winfo_screenheight() - h - 40))
    win.geometry(f"+{x}+{y}")


def place_dialog(win, parent):
    """作り終えてから、親ウインドウの真ん中に出す（左上に一瞬出ない）。ダイアログの __init__ の先頭で呼ぶ。"""
    win.withdraw()
    win.after_idle(lambda: (center_on(win, parent), win.deiconify(), win.lift(), win.focus_force()))

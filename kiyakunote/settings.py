"""画面とWord出力の表示設定（フォントの種類・大きさ）。利用者ごとに保存する（プロジェクトの外）。

保存先: %APPDATA%\KiyakuNote\settings.json（APPDATA が無い環境ではホームフォルダの .kiyakunote\settings.json）。
"""
import json
import os
from pathlib import Path

DEFAULTS = {
    "ui_family": "Yu Gothic UI", "ui_size": 11,          # ナビゲーション（メニュー・ボタン・説明）
    "text_family": "Yu Mincho", "text_size": 13,         # 条文・新旧対照表の表示欄
    "input_family": "Yu Gothic UI", "input_size": 12,    # 入力欄・編集フォーム
    "docx_family": "", "docx_size": 0,                   # Word出力（空・0 は従来どおり MS 明朝 10.5pt）
}
LIMITS = {"ui_size": (9, 28), "text_size": (9, 36), "input_size": (9, 28), "docx_size": (0, 24)}


def settings_path():
    base = os.environ.get("APPDATA")
    return (Path(base) / "KiyakuNote" if base else Path.home() / ".kiyakunote") / "settings.json"


def clean(d):
    """読み込んだ値を、使える値に直す（壊れた設定でも起動できるように）。"""
    out = dict(DEFAULTS)
    for k, default in DEFAULTS.items():
        v = d.get(k, default)
        if k == "docx_size":
            try:
                v = round(min(max(float(v), 0), 24) * 2) / 2
            except (TypeError, ValueError):
                v = 0
            out[k] = int(v) if v == int(v) else v
            continue
        if isinstance(default, int):
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = default
            lo, hi = LIMITS[k]
            v = min(max(v, lo), hi)
        else:
            v = str(v).strip() if v is not None else default
            if not v and k != "docx_family":
                v = default
        out[k] = v
    return out


def load(path=None):
    path = Path(path) if path else settings_path()
    try:
        return clean(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(d, path=None):
    path = Path(path) if path else settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(d), ensure_ascii=False, indent=2), encoding="utf-8")

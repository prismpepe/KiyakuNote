"""Markdown のファイルを、外部の Markdown エディタ（例: Handy Markdown Editor）で開く。画面を使わない。

設定の md_editor に実行ファイルのパスがあればそれで、無ければ Windows の関連づけ（既定のアプリ）で開く。
"""
import os
import subprocess
from pathlib import Path


def resolve_editor(path_setting):
    """設定のパスが実在すればそれ。無ければ None（関連づけで開く）。"""
    p = (path_setting or "").strip().strip('"')
    return p if p and Path(p).is_file() else None


def open_file(path, editor=None):
    """path をエディタで開く。editor が None なら関連づけで開く。起動できなければ OSError。"""
    path = Path(path)
    if not path.exists():
        raise OSError(f"ファイルがありません: {path}")
    if editor:
        subprocess.Popen([editor, str(path)], cwd=str(path.parent))
    else:
        os.startfile(str(path))                                     # noqa: S606


def file_for_node(iid, reg, src_dir):
    """左の一覧の項目に対応するファイル。無ければ None。"""
    src_dir = Path(src_dir)
    if iid == "@sign":
        return src_dir / "okugaki.txt"
    if iid == "@history":
        return src_dir / "revisions.yaml"
    d = reg.docs.get(iid.split("|", 1)[0])
    return Path(d.path) if d is not None else None

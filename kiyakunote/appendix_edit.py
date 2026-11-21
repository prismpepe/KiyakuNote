"""別表・別紙・別図の編集（表のセル、画像の差し替え、新設、削除）。画面を使わず、ファイルを書き換える。

前提: 別表・別紙・別図は src/ の中の1つのMarkdownファイル（先頭の --- の間がメタ情報、あとが本文）。
番号は、親文書（規約）の appendices: [tbl-1:1, app-1:1, ...] の並びと「id:番号」で決まる。削除しても番号は詰めない。
"""
import re
import shutil
from pathlib import Path

from .tables import render_html_table, render_md_table, replace_table

KIND_PREFIX = {"別表": "tbl", "別紙": "app", "別図": "fig"}
IMG = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


class AppendixError(Exception):
    pass


def split_file(text):
    """ファイルの文字列を (メタ情報の文字列（--- を含む）, 本文) に分ける。"""
    m = re.match(r"^(﻿?---[ \t]*\r?\n.*?\r?\n---[ \t]*\r?\n)(.*)$", text, re.S)
    if not m:
        raise AppendixError("先頭のメタ情報（---）が読めません")
    return m.group(1), m.group(2)


def read(path):
    return split_file(Path(path).read_text(encoding="utf-8-sig"))


def write(path, head, body):
    Path(path).write_text(head + body, encoding="utf-8", newline="\n")


def set_front(head, key, value):
    """メタ情報の key を value にする（無ければ末尾の --- の前に足す）。value が None なら取り除く。"""
    lines = head.rstrip("\n").split("\n")
    end = len(lines) - 1                                  # 閉じの ---
    for i in range(1, end):
        if re.match(rf"^{re.escape(key)}\s*:", lines[i]):
            if value is None:
                del lines[i]
            else:
                lines[i] = f"{key}: {value}"
            return "\n".join(lines) + "\n"
    if value is not None:
        lines.insert(end, f"{key}: {value}")
    return "\n".join(lines) + "\n"


# ---- 表のセルの編集 ----
def save_table(path, index, rows):
    """index 番目の表を、rows（行×列の文字）で書き換える。"""
    head, body = read(path)
    if not rows or not rows[0]:
        raise AppendixError("表には、1行1列以上が要ります")
    write(path, head, replace_table(body, index, rows))


# ---- 画像の差し替え ----
def images_in(body):
    return [(m.group(1), m.group(2)) for m in IMG.finditer(body)]


def unique_asset(assets_dir, doc_id, src_file):
    assets_dir = Path(assets_dir)
    ext = Path(src_file).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9_-]+", "", Path(src_file).stem)[:24]
    base = f"{doc_id}-{stem}" if stem else doc_id
    n, name = 1, f"{base}{ext}"
    while (assets_dir / name).exists():
        n += 1
        name = f"{base}-{n}{ext}"
    return name


def replace_image(path, index, image_file, assets_dir=None):
    """本文の index 番目の画像を、image_file（コピーして assets/ に置く）に差し替える。古い画像のファイルは残す。"""
    image_file = Path(image_file)
    if image_file.suffix.lower() not in EXTS:
        raise AppendixError("画像は png / jpg / gif / webp の形式で選んでください")
    path = Path(path)
    head, body = read(path)
    imgs = list(IMG.finditer(body))
    if not imgs:
        raise AppendixError("この別紙・別図には画像がありません")
    if not 0 <= index < len(imgs):
        raise AppendixError("差し替える画像の番号が正しくありません")
    assets = Path(assets_dir) if assets_dir else path.parent / "assets"
    assets.mkdir(exist_ok=True)
    name = unique_asset(assets, path.stem, image_file)
    shutil.copyfile(image_file, assets / name)
    m = imgs[index]
    body = body[:m.start()] + f"![{m.group(1)}](assets/{name})" + body[m.end():]
    write(path, head, body)
    return name


# ---- 新設・削除 ----
def appendix_entries(parent_head):
    m = re.search(r"(?m)^appendices\s*:\s*\[(.*)\]\s*$", parent_head)
    return [x.strip() for x in m.group(1).split(",") if x.strip()] if m else []


def next_number(reg, parent_id, kind):
    """親文書の同じ種類（別表・別紙・別図）の、次の番号。削除したものの番号も使い続ける（詰めない）。"""
    parent = reg.docs[parent_id]
    n, mx = 0, 0
    for ent in parent.meta.get("appendices", []):
        eid, _, num = ent.partition(":")
        n = int(num) if num else n + 1
        d = reg.docs.get(eid)
        if d is not None and d.kind == kind:
            mx = max(mx, n)
    return mx + 1


def new_id(reg, kind):
    prefix = KIND_PREFIX[kind]
    n = 1
    while f"{prefix}-{n}" in reg.docs:
        n += 1
    return f"{prefix}-{n}"


def create_appendix(reg, parent_id, kind, title, image_file=None, ncols=2, nrows=3, src_dir=None):
    """別表・別紙・別図を新設する。(新しい文書のパス, 親のパス, 親の元の内容) を返す（元に戻すため）。
    image_file があれば画像、なければ表（ncols × nrows の枠）を本文にする。"""
    if kind not in KIND_PREFIX:
        raise AppendixError("種類は 別表・別紙・別図 から選んでください")
    title = title.strip()
    if not title:
        raise AppendixError("名前（題名）を入れてください")
    parent = reg.docs[parent_id]
    src_dir = Path(src_dir) if src_dir else Path(parent.path).parent
    did = new_id(reg, kind)
    num = next_number(reg, parent_id, kind)
    path = src_dir / f"{did}.md"
    if path.exists():
        raise AppendixError(f"{path.name} はすでにあります")
    if image_file:
        assets = src_dir / "assets"
        assets.mkdir(exist_ok=True)
        name = unique_asset(assets, did, image_file)
        if Path(image_file).suffix.lower() not in EXTS:
            raise AppendixError("画像は png / jpg / gif / webp の形式で選んでください")
        shutil.copyfile(image_file, assets / name)
        body = f"![{title}](assets/{name})\n"
    else:
        rows = [[f"項目{c + 1}" for c in range(max(1, ncols))]] + [["" for _ in range(max(1, ncols))] for _ in range(max(1, nrows) - 1)]
        body = render_md_table(rows) + "\n"
    head = f"---\ndoc: {did}\nkind: {kind}\ntitle: {title}\nparent: {parent_id}\n---\n\n"
    ppath = Path(parent.path)
    old_parent = ppath.read_bytes()
    phead, pbody = read(ppath)
    ents = appendix_entries(phead)
    ents.append(f"{did}:{num}")
    if re.search(r"(?m)^appendices\s*:", phead):
        phead = re.sub(r"(?m)^appendices\s*:.*$", "appendices: [" + ", ".join(ents) + "]", phead)
    else:
        phead = set_front(phead, "appendices", "[" + ", ".join(ents) + "]")
    write(ppath, phead, pbody)
    path.write_text(head + body, encoding="utf-8", newline="\n")
    return path, ppath, old_parent


def delete_appendix(path):
    """別表・別紙・別図を削除する（番号の枠と ID は残し、本文を空にして deleted: true にする）。"""
    path = Path(path)
    head, body = read(path)
    if re.search(r"(?m)^deleted\s*:\s*true\s*$", head):
        raise AppendixError("すでに削除されています")
    write(path, set_front(head, "deleted", "true"), "")

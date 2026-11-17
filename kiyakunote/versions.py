"""版（改正）の管理。revisions.yaml と、git の履歴から過去の版を取り出す。

版は「総会決議日・施行日」の単位。gitのコミットとは別に持つ。
revisions.yaml の ref に git の参照（タグなど）を書いた版は、その時点の src/ を取り出して
条文を再現できる。ref の無い版は、改訂履歴の記録だけで本文は保持していない。
"""
import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from .core import Registry, load_dir

# 実行ファイル（PyInstaller）にしたときは、exeのあるフォルダを作業フォルダ（src/ がある所）とする
if getattr(__import__("sys"), "frozen", False):
    _exe = Path(__import__("sys").executable).resolve().parent
    # exe のあるフォルダ、またはその上位（app/KiyakuNote/ からプロジェクトへ）で src/ がある所
    ROOT = next((c for c in (_exe, _exe.parent, _exe.parent.parent) if (c / "src").is_dir()), _exe)
else:
    ROOT = Path(__file__).resolve().parent.parent
ERA = {"S": 1925, "H": 1988, "R": 2018}


def to_iso(s):
    """「H18.04.16」「2020.07.18」を 2006-04-16 の形にする。空なら空。"""
    s = s.strip()
    if not s:
        return ""
    m = re.match(r"^([SHR])(\d+)\.(\d+)\.(\d+)$", s)
    if m:
        y = ERA[m.group(1)] + int(m.group(2))
        return f"{y:04d}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"
    m = re.match(r"^(\d{4})\.(\d+)\.(\d+)$", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    raise ValueError(f"日付を読めない: {s}")


def parse_history(src_html):
    """改訂履歴の表を、版のリストにする。

    総会日のある行で新しい版が始まる。総会日のない行に施行日だけあるときは、
    直前の版に施行日が無ければそれを施行日とし、あれば同じ総会日の別の施行日の版にする。
    """
    revs = []
    cur = None
    for row in re.findall(r"<tr>(.*?)</tr>", src_html, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(cells) != 3 or cells[0] == "総会日":
            continue
        res, eff, content = (to_iso(cells[0]), to_iso(cells[1]), cells[2].replace("\u3000", " "))
        if res:
            cur = {"resolution": res, "effective": eff, "changes": [], "notes": []}
            revs.append(cur)
        elif eff:
            if cur is not None and not cur["effective"]:
                cur["effective"] = eff
            else:
                cur = {"resolution": cur["resolution"] if cur else "", "effective": eff,
                       "changes": [], "notes": []}
                revs.append(cur)
        if content:
            (cur["notes"] if "改定履歴" in content and not content.startswith("・") else cur["changes"]).append(
                content.lstrip("・").strip())
    return revs


def dump_revisions(revs):
    out = ["# 版（改正）の一覧。resolution=総会決議日、effective=施行日、ref=その版の条文を持つgitの参照（空なら記録のみ）",
           "revisions:"]
    for r in revs:
        out.append(f"  - resolution: {r['resolution']}")
        out.append(f"    effective: {r['effective']}")
        out.append(f"    ref: {r.get('ref', '')}")
        for n in r.get("notes", []):
            out.append(f"    note: {n}")
        out.append("    changes:")
        for c in r["changes"]:
            out.append(f"      - {c}")
    return "\n".join(out) + "\n"


def load_revisions(path=None):
    path = Path(path or ROOT / "src" / "revisions.yaml")
    revs = []
    cur = None
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.lstrip().startswith("#") or ln.strip() == "revisions:":
            continue
        m = re.match(r"^  - (\w+): ?(.*)$", ln)
        if m:
            cur = {"changes": [], "notes": []}
            revs.append(cur)
            cur[m.group(1)] = m.group(2).strip()
            continue
        m = re.match(r"^    (\w+): ?(.*)$", ln)
        if m and cur is not None:
            if m.group(1) == "note":
                cur["notes"].append(m.group(2).strip())
            elif m.group(1) != "changes":
                cur[m.group(1)] = m.group(2).strip()
            continue
        m = re.match(r"^      - (.*)$", ln)
        if m and cur is not None:
            cur["changes"].append(m.group(1).strip())
    return revs


def resolve(spec, revs=None):
    """版の指定を git の参照に直す。'WORKTREE'、'@2022-04-01'（その日に有効な版）、gitの参照そのまま。"""
    if spec == "WORKTREE" or spec.startswith("git:"):
        return spec.removeprefix("git:")
    if spec.startswith("@"):
        date = spec[1:]
        revs = revs if revs is not None else load_revisions()
        cands = [r for r in revs if r.get("ref") and r["effective"] and r["effective"] <= date]
        if not cands:
            raise ValueError(f"{date} に有効な、条文を保持している版がない")
        return max(cands, key=lambda r: r["effective"])["ref"]
    return spec


def run_quiet(cmd, **kw):
    """外部コマンドを、画面（コンソール）を出さずに実行する。

    画面のないアプリ（exe・pythonw）では標準入力が無効なので、子プロセスには明示的に空の入力を渡す。
    渡さないと「ハンドルが無効」で失敗する。
    """
    kw.setdefault("stdin", subprocess.DEVNULL)
    kw.setdefault("capture_output", True)
    if sys.platform == "win32":
        kw.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    return subprocess.run(cmd, **kw)


def load_version(ref, repo=ROOT):
    """git の参照（または WORKTREE）の src/ を読み込んで Registry にする。"""
    if ref == "WORKTREE":
        return Registry(load_dir(repo / "src"))
    names = run_quiet(["git", "ls-tree", "-r", "--name-only", ref, "src/"], cwd=repo,
                      check=True).stdout.decode("utf-8").split("\n")
    tmp = Path(tempfile.mkdtemp(prefix="kiyakunote-"))
    for n in names:
        n = n.strip().strip('"')
        if not n.endswith(".md"):
            continue
        data = run_quiet(["git", "show", f"{ref}:{n}"], cwd=repo, check=True).stdout
        p = tmp / Path(n).name
        p.write_bytes(data)
    return Registry(load_dir(tmp))

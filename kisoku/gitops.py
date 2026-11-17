"""変更の記録（git のコミット）と、版の登録（タグ・revisions.yaml）。GUIから使う。

改正の確定の流れ: src/ の変更をコミット → 施行日のタグを付ける → revisions.yaml に版を追加してコミット。
"""
import re
from datetime import date
from pathlib import Path

from .compare import appendix_changes, compare_doc
from .versions import dump_revisions, load_revisions, run_quiet

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class GitError(Exception):
    pass


def git(repo, *args, check=True):
    try:
        p = run_quiet(["git", *args], cwd=str(repo))
    except FileNotFoundError:
        raise GitError("git が見つかりません。git をインストールしてください。")
    out = p.stdout.decode("utf-8", "replace").strip()
    err = p.stderr.decode("utf-8", "replace").strip()
    if check and p.returncode != 0:
        raise GitError(err or out or f"git {args[0]} に失敗しました")
    return out


def is_repo(repo):
    try:
        return git(repo, "rev-parse", "--is-inside-work-tree", check=False) == "true"
    except GitError:
        return False


def changed_files(repo, path="src"):
    """未記録の変更のあるファイル [(状態, パス)]。画像（assets）も含む。"""
    out = git(repo, "status", "--porcelain", "--", path)
    rows = []
    for ln in out.splitlines():
        if ln.strip():
            rows.append((ln[:2].strip() or "?", ln[3:].strip().strip('"')))
    return rows


def commit(repo, message, path="src"):
    """src/ の変更をコミットする。コミットのIDを返す。"""
    message = message.strip()
    if not message:
        raise GitError("記録の説明を入れてください")
    if not changed_files(repo, path):
        raise GitError("記録する変更がありません")
    git(repo, "add", "-A", "--", path)
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "--short", "HEAD")


def validate_revision(repo, resolution, effective, tag, revs=None):
    errors = []
    if not DATE.match(resolution):
        errors.append("総会決議日は 2027-04-18 の形で入れてください")
    if not DATE.match(effective):
        errors.append("施行日は 2027-06-01 の形で入れてください")
    for d in (resolution, effective):
        if DATE.match(d):
            try:
                date.fromisoformat(d)
            except ValueError:
                errors.append(f"存在しない日付です: {d}")
    if not errors and resolution > effective:
        errors.append("総会決議日が施行日より後になっています")
    if not re.match(r"^[A-Za-z0-9._-]+$", tag or ""):
        errors.append("タグ名は英数字と . _ - だけで入れてください（例 v2027-06-01）")
    elif git(repo, "tag", "--list", tag):
        errors.append(f"タグ {tag} はすでにあります")
    revs = revs if revs is not None else load_revisions(Path(repo) / "src" / "revisions.yaml")
    if any(r.get("effective") == effective and r.get("ref") for r in revs):
        errors.append(f"施行日 {effective} の、条文を持つ版がすでにあります")
    return errors


def suggest_changes(reg_old, reg_new):
    """2つの版の差から、改訂履歴に書く「改定内容」の行を作る（人が直せる下書き）。"""
    lines = []
    ids = [i for i, d in reg_new.docs.items() if d.kind not in ("別表", "別紙", "別図")]
    ids += [i for i in reg_old.docs if i not in ids and reg_old.docs[i].kind not in ("別表", "別紙", "別図")]
    for did in ids:
        d_old, d_new = reg_old.docs.get(did), reg_new.docs.get(did)
        d = d_new or d_old
        name = "管理規約本文" if d.id == "kiyaku" else d.title
        if d_old is None:
            lines.append(f"{name} 制定")
        elif d_new is None:
            lines.append(f"{name} 廃止")
        elif any(k in ("新設", "削除", "改正") for k, _, _ in compare_doc(reg_old, reg_new, did)):
            lines.append(f"{name} 改定")
    for did, title, kind in appendix_changes(reg_old, reg_new):
        d = reg_new.docs.get(did) or reg_old.docs[did]
        n = reg_new.appendix_no(d) if did in reg_new.docs else None
        label = "管理規約別図" if d.kind == "別図" else (
            f"管理規約別表第{n}" if d.kind == "別表" else f"管理規約別紙{n}")
        lines.append(f"{label} {'制定' if kind == '新設' else '廃止' if kind == '削除' else '改定'}")
    return lines


def register_revision(repo, resolution, effective, tag, changes, note="", message=None):
    """タグを付け、revisions.yaml に版を加えてコミットする。src/ に未記録の変更があってはいけない。"""
    repo = Path(repo)
    if changed_files(repo, "src"):
        raise GitError("src/ に未記録の変更があります。先に「変更を記録」してください")
    errors = validate_revision(repo, resolution, effective, tag)
    if errors:
        raise GitError("\n".join(errors))
    git(repo, "tag", tag)
    path = repo / "src" / "revisions.yaml"
    revs = load_revisions(path)
    new = {"resolution": resolution, "effective": effective, "ref": tag,
           "notes": [note] if note.strip() else [], "changes": [c.strip() for c in changes if c.strip()]}
    pos = len(revs)
    for i, r in enumerate(revs):
        if (r.get("effective") or "") > effective:
            pos = i
            break
    revs.insert(pos, new)
    path.write_text(dump_revisions(revs), encoding="utf-8", newline="\n")
    git(repo, "add", "--", "src/revisions.yaml")
    git(repo, "commit", "-m", message or f"{effective} 施行の版を登録した（{tag}）")
    return tag

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
        errors.append("総会決議日は 2030-04-21 の形で入れてください")
    if not DATE.match(effective):
        errors.append("施行日は 2030-06-01 の形で入れてください")
    for d in (resolution, effective):
        if DATE.match(d):
            try:
                date.fromisoformat(d)
            except ValueError:
                errors.append(f"存在しない日付です: {d}")
    if not errors and resolution > effective:
        errors.append("総会決議日が施行日より後になっています")
    if not re.match(r"^[A-Za-z0-9._-]+$", tag or ""):
        errors.append("タグ名は英数字と . _ - だけで入れてください（例 v2030-06-01）")
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


# ---- 変更履歴・復元・設定（GUIの「変更履歴」タブから使う） ----
class GitIdentityError(GitError):
    """git の利用者名・メールが未設定。"""


def commit_safe(repo, message, path="src"):
    """commit と同じ。利用者名が未設定のときは GitIdentityError を出す（画面で設定を案内するため）。"""
    try:
        return commit(repo, message, path)
    except GitError as e:
        s = str(e)
        if "tell me who you are" in s or "empty ident" in s or "user.name" in s or "user.email" in s:
            raise GitIdentityError("git の利用者名とメールアドレスが未設定です。") from e
        raise


def user_identity(repo):
    """(名前, メール)。未設定は空文字。"""
    return (git(repo, "config", "user.name", check=False), git(repo, "config", "user.email", check=False))


def set_user_identity(name, email, repo=None):
    """利用者名・メールを、この利用者のgit全体の設定（--global）にする。"""
    name, email = name.strip(), email.strip()
    if not name or "@" not in email:
        raise GitError("名前と、@ を含むメールアドレスを入れてください")
    git(repo or ".", "config", "--global", "user.name", name)
    git(repo or ".", "config", "--global", "user.email", email)


def log(repo, limit=300, path="src"):
    """記録の履歴 [{id, date, message, tags}]。新しい順。"""
    out = git(repo, "log", f"-n{limit}", "--date=format:%Y-%m-%d %H:%M", "--pretty=format:%h%x09%ad%x09%s%x09%D", "--", path)
    rows = []
    for ln in out.splitlines():
        parts = ln.split("\t")
        if len(parts) < 3:
            continue
        deco = parts[3] if len(parts) > 3 else ""
        tags = [x.strip()[5:] for x in deco.split(",") if x.strip().startswith("tag: ")]
        rows.append({"id": parts[0], "date": parts[1], "message": parts[2], "tags": tags})
    return rows


def diff_text(repo, rev=None, path="src", limit=300000):
    """変更の内容（unified diff）。rev=None は「未記録の変更」、rev を指定するとその記録での変更。"""
    if rev:
        out = git(repo, "show", "--date=format:%Y-%m-%d %H:%M", "--stat", "--patch", "--format=【%h】%ad%n%s%n", rev, "--", path)
    else:
        out = git(repo, "diff", "HEAD", "--stat", "--patch", "--", path)
        new = [p for st, p in changed_files(repo, path) if st in ("?", "??")]
        if new:
            out += "\n\n（まだ記録されていない新しいファイル）\n" + "\n".join("  + " + p for p in new)
    return out[:limit] + ("\n…（長いので途中までです）" if len(out) > limit else "")


def discard_changes(repo, path="src"):
    """未記録の変更をすべて捨てて、最後に記録した状態に戻す（元に戻せない）。"""
    git(repo, "checkout", "HEAD", "--", path)
    git(repo, "clean", "-fd", "--", path)


def restore_to(repo, rev, path="src"):
    """path の中身を、記録 rev の状態にする（未記録の変更として残るので、あとで「変更を記録」する）。"""
    if changed_files(repo, path):
        raise GitError("未記録の変更があります。先に記録するか、破棄してください")
    now = set(git(repo, "ls-tree", "-r", "--name-only", "HEAD", "--", path).splitlines())
    then = set(git(repo, "ls-tree", "-r", "--name-only", rev, "--", path).splitlines())
    for extra in sorted(now - then):
        git(repo, "rm", "-q", "-f", "--", extra.strip('"'))
    git(repo, "checkout", rev, "--", path)

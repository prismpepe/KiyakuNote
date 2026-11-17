"""変更の記録と版の登録（一時のgitリポジトリで行う）。"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kiyakunote import edit, gitops  # noqa: E402
from kiyakunote.versions import dump_revisions, load_revisions, load_version, resolve  # noqa: E402


def sh(repo, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=repo, check=True,
                   capture_output=True)


class GitOpsTest(unittest.TestCase):
    def setUp(self):
        if shutil.which("git") is None:
            self.skipTest("git がない")
        self.repo = Path(tempfile.mkdtemp())
        src = self.repo / "src"
        src.mkdir()
        for f in (ROOT / "tests" / "fixtures").glob("*.md"):
            if not f.name.startswith("expected"):
                shutil.copy(f, src / f.name)
        revs = [{"resolution": "2026-04-19", "effective": "2026-06-01", "ref": "v2026-06-01",
                 "notes": [], "changes": ["管理規約本文 改定"]}]
        (src / "revisions.yaml").write_text(dump_revisions(revs), encoding="utf-8")
        sh(self.repo, "init", "-q")
        sh(self.repo, "add", "-A")
        sh(self.repo, "commit", "-qm", "初版")
        sh(self.repo, "tag", "v2026-06-01")
        # このリポジトリ内のコミットだけで使えるよう、ユーザー設定をローカルに置く
        sh(self.repo, "config", "user.name", "t")
        sh(self.repo, "config", "user.email", "t@t")

    def test_commit_and_register(self):
        self.assertEqual(gitops.changed_files(self.repo), [])
        doc = edit.load_for_edit(self.repo / "src" / "kiyaku.md")
        edit.edit_article(doc, "art-purpose", "目的", "項 改めた本文。")
        edit.save(doc)
        self.assertTrue(gitops.changed_files(self.repo))
        with self.assertRaises(gitops.GitError):             # 未記録の変更があると登録できない
            gitops.register_revision(self.repo, "2027-04-18", "2027-06-01", "v2027-06-01", ["管理規約本文 改定"])
        gitops.commit(self.repo, "目的の文言を改めた")
        self.assertEqual(gitops.changed_files(self.repo), [])
        # 登録前に、版の差から改定内容の下書きを作れる
        old = load_version("v2026-06-01", self.repo)
        new = load_version("WORKTREE", self.repo)
        self.assertEqual(gitops.suggest_changes(old, new), ["管理規約本文 改定"])
        gitops.register_revision(self.repo, "2027-04-18", "2027-06-01", "v2027-06-01", ["管理規約本文 改定"], "試験")
        revs = load_revisions(self.repo / "src" / "revisions.yaml")
        self.assertEqual([r["effective"] for r in revs], ["2026-06-01", "2027-06-01"])
        self.assertEqual(revs[-1]["ref"], "v2027-06-01")
        self.assertEqual(gitops.git(self.repo, "tag", "--list", "v2027-06-01"), "v2027-06-01")
        # 日付で版を取り出せる
        self.assertEqual(resolve("@2027-07-01", revs), "v2027-06-01")
        self.assertEqual(resolve("@2026-12-01", revs), "v2026-06-01")
        self.assertEqual(gitops.changed_files(self.repo), [])

    def test_validation(self):
        errs = gitops.validate_revision(self.repo, "2027/4/18", "2027-06-01", "v 1")
        self.assertTrue(any("総会決議日" in e for e in errs))
        self.assertTrue(any("タグ名" in e for e in errs))
        errs = gitops.validate_revision(self.repo, "2027-04-18", "2026-06-01", "v2026-06-01")
        self.assertTrue(any("すでにあります" in e for e in errs))
        errs = gitops.validate_revision(self.repo, "2027-07-01", "2027-06-01", "v2027-06-01")
        self.assertTrue(any("後" in e for e in errs))


if __name__ == "__main__":
    unittest.main()

"""表示設定・変更履歴（git の操作）・Word出力のフォント設定の確認。画面（Tk）は使わない。"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kiyakunote import docx_out, gitops, settings  # noqa: E402


def run(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


class SettingsTest(unittest.TestCase):
    def test_roundtrip_and_clamp(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            self.assertEqual(settings.load(p), settings.DEFAULTS)           # ファイルが無ければ既定
            settings.save({"ui_size": 99, "text_size": 1, "text_family": "MS 明朝", "docx_size": 10.5}, p)
            c = settings.load(p)
            self.assertEqual(c["ui_size"], 28)                              # 大きすぎる値は上限に丸める
            self.assertEqual(c["text_size"], 9)
            self.assertEqual(c["text_family"], "MS 明朝")
            self.assertEqual(c["docx_size"], 10.5)
            p.write_text("壊れた内容", encoding="utf-8")
            self.assertEqual(settings.load(p), settings.DEFAULTS)           # 壊れていても起動できる

    def test_docx_configure(self):
        try:
            docx_out.configure("Meiryo", 12)
            self.assertEqual((docx_out.FONT, docx_out.SIZE), ("Meiryo", 12.0))
            docx_out.configure("", 0)
            self.assertEqual((docx_out.FONT, docx_out.SIZE), (docx_out.DEFAULT_FONT, docx_out.DEFAULT_SIZE))
        finally:
            docx_out.configure("", 0)


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        for a in (("init", "-q"), ("config", "user.name", "t"), ("config", "user.email", "t@example.com")):
            run(self.repo, *a)
        (self.repo / "src").mkdir()
        (self.repo / "src" / "a.md").write_text("first\n", encoding="utf-8")
        gitops.git(self.repo, "add", "-A")
        gitops.git(self.repo, "commit", "-q", "-m", "最初")
        gitops.git(self.repo, "tag", "v1")
        (self.repo / "src" / "a.md").write_text("second\n", encoding="utf-8")
        (self.repo / "src" / "b.md").write_text("new\n", encoding="utf-8")
        gitops.commit(self.repo, "2回目")

    def tearDown(self):
        self.tmp.cleanup()

    def test_log_and_diff(self):
        rows = gitops.log(self.repo)
        self.assertEqual([r["message"] for r in rows], ["2回目", "最初"])
        self.assertEqual(rows[1]["tags"], ["v1"])
        self.assertIn("+second", gitops.diff_text(self.repo, rows[0]["id"]))
        (self.repo / "src" / "a.md").write_text("third\n", encoding="utf-8")
        (self.repo / "src" / "c.md").write_text("untracked\n", encoding="utf-8")
        d = gitops.diff_text(self.repo)
        self.assertIn("+third", d)
        self.assertIn("c.md", d)

    def test_discard(self):
        (self.repo / "src" / "a.md").write_text("junk\n", encoding="utf-8")
        (self.repo / "src" / "c.md").write_text("junk\n", encoding="utf-8")
        gitops.discard_changes(self.repo)
        self.assertEqual((self.repo / "src" / "a.md").read_text(encoding="utf-8"), "second\n")
        self.assertFalse((self.repo / "src" / "c.md").exists())
        self.assertEqual(gitops.changed_files(self.repo), [])

    def test_restore_keeps_history(self):
        first = gitops.log(self.repo)[1]["id"]
        gitops.restore_to(self.repo, first)
        self.assertEqual((self.repo / "src" / "a.md").read_text(encoding="utf-8"), "first\n")
        self.assertFalse((self.repo / "src" / "b.md").exists())            # その時点に無かったファイルは消える
        self.assertTrue(gitops.changed_files(self.repo))                  # 未記録の変更として残る
        self.assertEqual(len(gitops.log(self.repo)), 2)                   # 履歴は消えない
        with self.assertRaises(gitops.GitError):
            gitops.restore_to(self.repo, first)                            # 未記録の変更があるときは戻せない


if __name__ == "__main__":
    unittest.main()

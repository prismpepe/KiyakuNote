"""同梱のサンプル規約（src/、架空の「サンプルハイツ」）が、記法どおりに読めて出力できることを確かめる。

2版（2018年制定・2022年改正）はタグ v2018-04-01 / v2022-04-01 から読む。タグは git のクローンに入っている。
"""
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kisoku.compare import compare_doc  # noqa: E402
from kisoku.core import Registry, load_dir  # noqa: E402
from kisoku.lint import lint  # noqa: E402
from kisoku.render import article_text  # noqa: E402
from kisoku.versions import load_revisions, load_version, resolve  # noqa: E402


def label(a):
    return f"第{a.number}条" + (f"の{a.branch_no}" if a.branch_no else "")


@unittest.skipIf(shutil.which("git") is None, "git がない")
class SampleProjectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = Registry(load_dir(ROOT / "src"))
        cls.kiyaku = cls.reg.docs["kiyaku"]

    def test_lint_clean(self):
        self.assertEqual([f for f in lint(self.reg) if f[0] in "EW"], [])

    def test_numbering_with_branch_and_deleted(self):
        by = {label(a): a for a in self.kiyaku.articles if not a.supplementary}
        self.assertIn("第5条の2", by)                      # 枝番の条
        self.assertTrue(by["第7条"].deleted)               # 削除（番号の枠を残す）
        self.assertEqual(by["第19条"].title, "電磁的方法による議決権の行使")

    def test_reference_follows_numbers(self):
        """参照はIDで書かれ、番号は出力時に計算される。"""
        a = next(x for x in self.kiyaku.articles if x.id == "art-bylaw")
        self.assertIn("第20条第1項第１号", article_text(self.reg, self.kiyaku, a))
        b = self.reg.docs["bylaw-parking"]
        self.assertIn("規約第25条第2項", article_text(self.reg, b, next(x for x in b.articles if x.id == "art-amend")))

    def test_revisions_resolve(self):
        revs = load_revisions(ROOT / "src" / "revisions.yaml")
        self.assertEqual(resolve("@2020-01-01", revs), "v2018-04-01")
        self.assertEqual(resolve("@2022-04-01", revs), "v2022-04-01")

    def test_compare_two_versions(self):
        old, new = load_version("v2018-04-01"), load_version("v2022-04-01")
        rows = compare_doc(old, new, "kiyaku")
        joined = " ".join(r[0] for r in rows)
        for want in ("新設", "削除", "改正", "条番号のみ変更", "参照の自動更新"):
            self.assertIn(want, joined)

    def test_old_version_text(self):
        old = load_version("v2018-04-01").docs["kiyaku"]
        a = next(x for x in old.articles if x.id == "art-assembly")
        self.assertIn("2か月以内", a.paras[2].text)


if __name__ == "__main__":
    unittest.main()

"""条の追加で番号が繰り下がる改正を作り、新旧対照表の分類を確かめる。"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kisoku.compare import compare_doc, render_table  # noqa: E402
from kisoku.core import Registry, load_dir  # noqa: E402


class CompareTest(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.old_dir, self.new_dir = tmp / "old", tmp / "new"
        for d in (self.old_dir, self.new_dir):
            d.mkdir()
            for f in (ROOT / "tests" / "fixtures").glob("*.md"):
                if not f.name.startswith("expected"):
                    shutil.copy(f, d / f.name)
        k = self.new_dir / "kiyaku.md"
        t = k.read_text(encoding="utf-8")
        # 目的の後ろに新しい条を入れる（以降の条番号が繰り下がる）。定義の本文も少し変える。
        t = t.replace("## {#art-def} 定義", "## {#art-new} 新設の条\n\nこれは新設した条である。\n\n## {#art-def} 定義")
        t = t.replace("用語の意義は", "用語の意味は")
        k.write_text(t, encoding="utf-8")
        self.old = Registry(load_dir(self.old_dir))
        self.new = Registry(load_dir(self.new_dir))

    def kinds(self):
        return {t.split("（")[0].split("\n")[0]: k for k, t, _ in []}

    def test_classification(self):
        rows = compare_doc(self.old, self.new, "kiyaku")
        by = {}
        for kind, old, new in rows:
            head = (new if kind != "削除" else old).split("\n")[0].replace("*", "").replace("~", "")
            by[head.split("（")[0]] = kind
        self.assertEqual(by["第2条"], "新設")             # 新設の条（見出しなし）
        self.assertEqual(by["第3条"], "改正")             # 定義の文言変更（番号も繰り下がる）
        self.assertEqual(by["第5条"], "参照の自動更新")   # 駐車場の使用（内容同じ、前項・条番号の参照が更新）
        self.assertEqual(by["第5条の2"], "条番号のみ変更")  # 駐車場使用料
        self.assertEqual(by["第6条"], "参照の自動更新")   # 使用契約の解除（第4条第1項→第5条第1項）

    def test_unchanged_doc(self):
        # 細則は文言が変わらず、参照先の条番号が変わる（規約第4条の2→第5条の2）
        rows = compare_doc(self.old, self.new, "bylaw-parking")
        self.assertEqual([k for k, _, _ in rows], ["参照の自動更新"])
        self.assertIn("規約第**5**条の2", rows[0][2])

    def test_table_renders(self):
        text = render_table(self.old, self.new, "旧", "新")
        self.assertIn("| 新設 |", text)
        self.assertIn("変更:", text)


if __name__ == "__main__":
    unittest.main()

"""tests/fixtures/ の出力が expected-kiyaku.md と一致することを確かめる。"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kiyakunote.core import Registry, load_dir  # noqa: E402
from kiyakunote.lint import lint  # noqa: E402
from kiyakunote.render import render_doc  # noqa: E402


def norm(s):
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"\n{2,}", "\n\n", s.replace("\r\n", "\n"))
    return s.strip()


class SampleTest(unittest.TestCase):
    def setUp(self):
        self.reg = Registry(load_dir(ROOT / "tests" / "fixtures"))

    def test_lint_clean(self):
        errors = [f for f in lint(self.reg) if f[0] == "E"]
        self.assertEqual(errors, [])

    def test_matches_expected(self):
        expected = (ROOT / "tests" / "fixtures" / "expected-kiyaku.md").read_text(encoding="utf-8")
        exp_kiyaku, exp_bylaw = [norm(x) for x in expected.split("\n---\n")]
        self.assertEqual(norm(render_doc(self.reg, self.reg.docs["kiyaku"])), exp_kiyaku)
        self.assertEqual(norm(render_doc(self.reg, self.reg.docs["bylaw-parking"])), exp_bylaw)


if __name__ == "__main__":
    unittest.main()

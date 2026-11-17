"""Word出力の確認（tests/fixtures/ と、新旧対照表）。"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kisoku.core import Registry, load_dir  # noqa: E402
from kisoku.docx_out import build_compare_docx, build_docx  # noqa: E402


def text_of(path):
    d = Document(str(path))
    out = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            out += [c.text for c in row.cells]
    return "\n".join(out)


class DocxTest(unittest.TestCase):
    def test_body_and_appendix(self):
        reg = Registry(load_dir(ROOT / "tests" / "fixtures"))
        p = Path(tempfile.mkdtemp()) / "k.docx"
        build_docx(reg, reg.docs["kiyaku"], p, src_dir=ROOT / "tests" / "fixtures")
        t = text_of(p)
        self.assertIn("第4条の2　駐車場の使用料の額は、別表第1のとおりとする。", t)   # 枝番・参照展開
        self.assertIn("（１）　区分所有者", t)                                          # 号の書式
        self.assertIn("第3条　削除", t)
        self.assertIn("別表第1（第4条の2関係）", t)
        self.assertIn("機械式上段", t)                                                  # 別表の表

    def test_compare(self):
        tmp = Path(tempfile.mkdtemp())
        for n in ("old", "new"):
            (tmp / n).mkdir()
            for f in (ROOT / "tests" / "fixtures").glob("*.md"):
                if not f.name.startswith("expected"):
                    shutil.copy(f, tmp / n / f.name)
        k = tmp / "new" / "kiyaku.md"
        k.write_text(k.read_text(encoding="utf-8").replace("用語の意義は", "用語の意味は"), encoding="utf-8")
        p = tmp / "c.docx"
        build_compare_docx(Registry(load_dir(tmp / "old")), Registry(load_dir(tmp / "new")), "旧", "新", p)
        t = text_of(p)
        self.assertIn("新旧対照表", t)
        self.assertIn("改正", t)


if __name__ == "__main__":
    unittest.main()

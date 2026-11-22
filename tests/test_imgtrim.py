"""別紙の画像のトリミング（余白とページ番号の除去）。画面（Tk）は使わない。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw  # noqa: E402
from kiyakunote.imgtrim import PAD, content_box  # noqa: E402


class TrimTest(unittest.TestCase):
    def page(self, number=True):
        im = Image.new("L", (1000, 1400), 255)
        d = ImageDraw.Draw(im)
        d.rectangle((120, 150, 880, 1200), outline=0, width=3)          # 本文の枠
        d.rectangle((300, 600, 700, 640), fill=0)
        if number:
            d.rectangle((492, 1300, 508, 1314), fill=0)                  # 下端中央のページ番号
        return im

    def test_trim_margin_and_page_number(self):
        l, t, r, b = content_box(self.page())
        self.assertEqual((l, t), (120 - PAD, 150 - PAD))
        self.assertTrue(880 + PAD - 2 <= r <= 880 + PAD + 3)
        self.assertLess(b, 1300)                                          # ページ番号は含めない

    def test_no_page_number_keeps_content(self):
        im = self.page(number=False)
        l, t, r, b = content_box(im)
        self.assertTrue(1200 < b <= 1200 + PAD + 3)

    def test_blank_page(self):
        self.assertEqual(content_box(Image.new("L", (100, 100), 255)), (0, 0, 100, 100))


if __name__ == "__main__":
    unittest.main()

"""GUIの起動確認（画面が使えない環境では飛ばす）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class GuiSmoke(unittest.TestCase):
    def test_start_and_search(self):
        try:
            import tkinter
            tkinter.Tk().destroy()
        except Exception:
            self.skipTest("画面が使えない")
        from kiyakunote.gui import App
        app = App()
        try:
            app.s_q.insert(0, "駐車場 使用料")
            app.do_search()
            self.assertTrue(app.s_hits)                                   # 結果が並ぶ
            self.assertTrue(app.s_list.tag_ranges("hit"))                 # 一致した語に黄色のマーカー
            app.s_re.set(True)
            app.s_q.delete(0, "end")
            app.s_q.insert(0, r"第\d+条")
            app.do_search()
            self.assertTrue(app.s_hits)
            app.do_lint()
            self.assertIn("エラー 0 件", app.l_info.cget("text"))
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()

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
        from kisoku.gui import App
        app = App()
        try:
            app.s_q.insert(0, "駐車場 使用料")
            app.do_search()
            self.assertTrue(app.s_tree.get_children())
            app.do_lint()
            self.assertIn("エラー 0 件", app.l_info.cget("text"))
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()

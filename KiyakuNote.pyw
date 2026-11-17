"""ダブルクリックでGUIを起動する（コンソール画面を出さない）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kiyakunote.gui import main  # noqa: E402

main()

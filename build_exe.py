"""GUIをexeにする（PyInstaller）。出力: app/KiyakuNote/KiyakuNote.exe

exe は、プロジェクトのフォルダ（src/ がある所）の中から起動すると、そのフォルダの src/ と git の履歴を使う。
python build_exe.py [--run]   --run: 作ったあとに起動する
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "KiyakuNote"


def main():
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--name", NAME,
           "--distpath", str(ROOT / "app"), "--workpath", str(ROOT / "out" / "build"),
           "--specpath", str(ROOT / "out"), str(ROOT / "KiyakuNote.pyw")]
    print(" ".join(cmd))
    if subprocess.call(cmd) != 0:
        print("\nexeの作成に失敗しました。PyInstaller が入っていない場合は: python -m pip install pyinstaller")
        return 1
    exe = ROOT / "app" / NAME / f"{NAME}.exe"
    print(f"\n作成しました: {exe}")
    if "--run" in sys.argv:
        # 親のコンソールとは切り離して起動する。Popen で起動すると、bat の黒い画面を閉じたときに
        # 一緒に終了してしまう（「画面が出てすぐ落ちる」原因になる）。
        import os
        os.startfile(str(exe))
    return 0


if __name__ == "__main__":
    sys.exit(main())

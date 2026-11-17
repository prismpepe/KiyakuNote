"""配布版（Windows 用の zip）を作る。出力: dist/KiyakuNote-<バージョン>-win.zip

exe を作り（PyInstaller が必要）、exe・サンプル規約（src/）・ドキュメントを1つのフォルダにまとめて zip にする。
展開したフォルダの KiyakuNote\\KiyakuNote.exe をダブルクリックすると起動する。
python build_release.py
"""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from kiyakunote import __version__  # noqa: E402

NAME = "KiyakuNote"
DOCS = ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md")


def main():
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", NAME,
           "--distpath", str(ROOT / "app"), "--workpath", str(ROOT / "out" / "build"),
           "--specpath", str(ROOT / "out"), str(ROOT / "KiyakuNote.pyw")]
    print(" ".join(cmd))
    if subprocess.call(cmd) != 0:
        print("\nexeの作成に失敗しました。PyInstaller が入っていない場合は: python -m pip install pyinstaller")
        return 1
    exe_dir = ROOT / "app" / NAME
    if not (exe_dir / f"{NAME}.exe").exists():
        print("exe が見つかりません:", exe_dir)
        return 1

    pkg = ROOT / "dist" / f"{NAME}-{__version__}-win"
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)
    shutil.copytree(exe_dir, pkg / NAME)
    shutil.copytree(ROOT / "src", pkg / "src")
    shutil.copytree(ROOT / "docs", pkg / "docs")
    for f in DOCS:
        if (ROOT / f).exists():
            shutil.copy2(ROOT / f, pkg)

    zip_path = ROOT / "dist" / f"{pkg.name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(pkg.rglob("*")):
            if p.is_file():
                z.write(p, Path(pkg.name) / p.relative_to(pkg))
    print(f"\n配布版を作りました: {zip_path}（{zip_path.stat().st_size / 1024 / 1024:.1f} MB）")
    print(f"展開して試す場合: {pkg}\\{NAME}\\{NAME}.exe")
    return 0


if __name__ == "__main__":
    sys.exit(main())

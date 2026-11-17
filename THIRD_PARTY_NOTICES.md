# 利用しているライブラリ

このリポジトリには、外部ライブラリのコードは含めていません。実行時に必要なもの、開発・配布のときに使うものは次のとおりです。

| 名前 | 用途 | ライセンス |
|------|------|-----------|
| Python（標準ライブラリ、tkinter、sqlite3） | 実行環境 | PSF License |
| [python-docx](https://github.com/python-openxml/python-docx) | Word（.docx）出力 | MIT |
| [pytest](https://pytest.org/)（開発） | テスト | MIT |
| [PyInstaller](https://pyinstaller.org/)（任意） | GUI を exe にする | GPL-2.0 に「バンドル例外」を付けたもの。作った exe は PyInstaller のライセンスに縛られず配布できます |
| [Pillow](https://python-pillow.org/)（任意） | スクリーンショットの撮影 | MIT-CMU（HPND） |

## 配布するとき（exe を作る場合）

PyInstaller で作った exe には、Python と python-docx（とその依存の lxml など）が同梱されます。
配布するときは、それぞれのライセンス表示を同梱してください。

## 規約の本文について

`src/` と `tests/fixtures/` の規約は、このリポジトリのために作った**架空の文書**です（CC0）。
国土交通省の「マンション標準管理規約」は同梱していません。使うときは、政府標準利用規約に従い、出典を明記してください。

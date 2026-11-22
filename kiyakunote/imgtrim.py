"""PDFのページを丸ごと画像にした別紙・別図から、余白とページ番号を切り落とす（画面を使わない）。

文字や罫線のある範囲を求め、いちばん下に離れて1つだけある小さな塊（中央付近のページ番号）は除く。
"""
import numpy as np
from PIL import Image

INK = 190                      # これより暗い画素を「インク」とみなす
PAD = 16                       # 切り落としたあとの周りの余白（画素）


def _bands(active, gap):
    """真偽の列から、gap 以内のすき間でつながる (開始, 終了) の区間を求める。"""
    bands, start, last = [], None, None
    for i, a in enumerate(active):
        if a:
            if start is None:
                start = i
            last = i
        elif start is not None and i - last > gap:
            bands.append((start, last))
            start = None
    if start is not None:
        bands.append((start, last))
    return bands


def content_box(im):
    """(左, 上, 右, 下)。インクが無ければ画像全体。ページ番号と思われる下端の小さな塊は含めない。"""
    g = np.asarray(im.convert("L"))
    h, w = g.shape
    ink = g < INK
    rows = ink.sum(axis=1) >= 3                           # ごみ（点）だけの行は無視
    bands = _bands(rows, max(4, h // 150))
    if not bands:
        return 0, 0, w, h
    limit = h                                              # 除いた塊より下は含めない（余白の PAD で食い込ませない）
    for k in range(1, len(bands)):                         # 下端に離れてある、小さな塊（ページ番号・その断片）のまとまりを除く
        top, bot = bands[k][0], bands[-1][1]
        cols = np.nonzero(ink[top:bot + 1].sum(axis=0) >= 1)[0]
        if not cols.size:
            limit = top - 1
            bands = bands[:k]
            break
        cx = (cols.min() + cols.max()) / 2
        small = (bot - top) < h * 0.04 and (cols.max() - cols.min()) < w * 0.15 and (w * 0.3 < cx < w * 0.7 or top > h * 0.9)
        if small and top - bands[k - 1][1] > h * 0.008:
            limit = top - 1
            bands = bands[:k]
            break
    y0, y1 = bands[0][0], bands[-1][1]
    cols = ink[y0:y1 + 1].sum(axis=0) >= 2
    xs = np.nonzero(cols)[0]
    if xs.size == 0:
        return 0, 0, w, h
    return max(0, xs.min() - PAD), max(0, y0 - PAD), min(w, xs.max() + 1 + PAD), min(h, y1 + 1 + PAD, limit)


def trim_image(path, out=None, quality=85):
    """画像を切り落として保存する（out が None なら上書き）。切り落とした後の大きさ (幅, 高さ) を返す。"""
    im = Image.open(path)
    im.load()
    box = content_box(im)
    cropped = im.crop(box)
    cropped.convert("RGB").save(out or path, "JPEG", quality=quality)
    return cropped.size

"""原図の「上の管理ヘッダー帯」だけを落とし、作画範囲（撮影フレーム＋移動用の余分）は
丸ごと残すための処理。

背景:
- 原図シート最上部には管理ヘッダー（作品名/カットNo/TIME/スタジオ名）＋タップ穴がある。
- シート全体を生成に渡すと、モデルが絵をシート全面に描き直し、ヘッダー帯のぶん絵が上にずれる
  （レジストが合わない）。→ ヘッダー帯だけ落とす。
- ただし撮影フレームより外側の「余分」（PAN/TU/SL用に大きめに描いた領域）は作画なので残す。
  カット毎にばらつくため、撮影フレームで切ってはいけない（§18.1）。
- 方針: ヘッダー文字帯の“下の白い隙間”で切り、左右・下は全幅・全高そのまま残す（広めでよい）。

撮影フレーム矩形は「映る範囲/PAN参照」のメタ情報。切る境界には使わない（detect_camera_frame）。
"""
from __future__ import annotations
import numpy as np
from PIL import Image


def header_bottom(image_path: str, text_lo: float = 0.10, text_hi: float = 0.155,
                  gap: float = 0.05, dark_th: int = 150) -> int:
    """管理ヘッダー帯の下端 y を推定する（2段方式）。

    DANGUN系の原図シートは上から「タップ穴の黒タブ → 印刷ヘッダー文字行
    (作品名/カットNo/TIME/スタジオ名) → 作画」の順に並ぶ。ヘッダー下端は
    実測で高さの ~0.14 に安定している。

    1段目: ヘッダー文字行を text_lo..text_hi 帯の「最も暗い行」として特定する
            （タップ穴の上の白帯を誤検出しないよう、探索帯はタブより下に置く）。
    2段目: その文字行の直下 gap 以内で「最も白い行」(=文字と作画の隙間)を切る位置にする。

    全幅の枠線(撮影フレーム)はスパイクだが、文字行より下の白帯探索では拾わない＝作画を切らない。
    注: 作画が上端から始まる非標準シート(空/雲・ノート多数等)では誤るので、その場合は
        strip_header(..., top_override=y) で明示的に与えること（§19 データ品質）。
    """
    im = np.asarray(Image.open(image_path).convert("L")).astype(float)
    H, _ = im.shape
    row_dark = (im < dark_th).mean(axis=1)
    a, b = int(H * text_lo), int(H * text_hi)
    if b <= a:
        return int(H * 0.14)
    y_text = a + int(np.argmax(row_dark[a:b]))   # 最暗行 = ヘッダー文字行
    lo = y_text + 2
    hi = min(H, y_text + int(H * gap))
    if hi <= lo:
        return y_text
    return lo + int(np.argmin(row_dark[lo:hi]))   # 文字の下の白い隙間


def strip_header(image_path: str, out_path: str, top_override: int | None = None):
    """ヘッダー帯だけ落として保存し、戻し用の領域 (left, top, right, bottom) を返す。
    左右・下は全幅・全高をそのまま残す（余分・PAN用を切らない）。
    top_override を渡すと自動検出を使わずその y で切る（非標準シート用）。
    """
    y = top_override if top_override is not None else header_bottom(image_path)
    im = Image.open(image_path).convert("RGB")
    W, H = im.size
    region = (0, y, W, H)
    im.crop(region).save(out_path)
    return region


def paste_into_region(canvas_size, region, content_path: str, out_path: str,
                      bg=(255, 255, 255)):
    """生成結果を元の領域(region)へ正確に戻し、フルキャンバス画像として保存する。
    region=(l,t,r,b)。領域外（＝落としたヘッダー帯）は bg で塗る。
    """
    l, t, r, b = region
    content = Image.open(content_path).convert("RGB").resize((r - l, b - t), Image.LANCZOS)
    canvas = Image.new("RGB", canvas_size, bg)
    canvas.paste(content, (l, t))
    canvas.save(out_path)
    return out_path


def detect_camera_frame(image_path: str, search: float = 0.33, k: float = 2.0):
    """撮影フレーム矩形 (l,t,r,b) の推定（メタ情報用。切る境界には使わない）。
    各辺外側 search 割合の帯で暗さ投影が突出する位置（枠線）を拾う。
    """
    im = np.asarray(Image.open(image_path).convert("L")).astype(float)
    a = 255.0 - im
    H, W = a.shape
    row, col = a.sum(1) / W, a.sum(0) / H

    def peak(p, lo, hi, from_start):
        th = p.mean() + k * p.std()
        idx = [i for i in range(lo, hi) if p[i] > th]
        if not idx:
            return None
        return min(idx) if from_start else max(idx)

    t = peak(row, 0, int(H * search), True)
    b = peak(row, int(H * (1 - search)), H, False)
    l = peak(col, 0, int(W * search), True)
    r = peak(col, int(W * (1 - search)), W, False)
    return (0 if l is None else l, 0 if t is None else t,
            W - 1 if r is None else r, H - 1 if b is None else b)

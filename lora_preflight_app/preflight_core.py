"""LoRA Preflight 画像整形コア。

設計: docs/lora-preflight/design-image-processing.md（リポジトリ側）

「Plan（計画=純データ）」と「Render（実行）」を分離する。
サムネも出力PNGも同じ apply_plan() の結果から作るので、画面と実ファイルが
ズレることが構造上ない（WYSIWYG保証）。Plan は JSON 化して manifest に残す。

UI・HTTP・ファイルIOには依存しない。依存は Pillow のみ。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

from PIL import Image, ImageChops

# 全身絵から作る4枚の種別（この順で _1.._4 を割り当てる）
FULLBODY_KINDS = ("fb_upper", "fb_body", "fb_feet", "fb_full")
KIND_LABELS = {
    "normal": "整形",
    "fb_upper": "上半身",
    "fb_body": "首から下",
    "fb_feet": "足元",
    "fb_full": "全身",
}


@dataclass(frozen=True)
class PreflightConfig:
    sizes: tuple = ((1024, 1024), (1152, 896), (1216, 832), (1344, 768), (1536, 640))
    allow_rotate: bool = True
    pad_crop_x: float = 0.5        # 0=余白優先 .. 1=切り取り優先
    max_crop_frac: float = 0.15    # 元面積に対する切除率がこれを超えたら別比率へ逃がす
    fullbody_base_height: int = 2200
    fullbody_tile: int = 1024
    neck_ratio: float = 0.14       # 首位置 = 頭頂 + neck_ratio * 人物高
    trim_threshold: int = 18
    head_margin_px: int = 16       # 高さ正規化後の空間での頭上/足下マージン


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int
    content_box: tuple  # (x0, y0, x1, y1) 内容範囲（元画像座標）
    bg_color: tuple     # (r, g, b)


@dataclass(frozen=True)
class CropPlan:
    """加工計画。apply_plan() は crop → pad → resize の順に適用する。"""

    kind: str                    # normal / fb_upper / fb_body / fb_feet / fb_full
    src_size: tuple              # (w, h) 元画像
    crop_box: tuple              # (l, t, r, b) 元画像座標
    pad: tuple                   # (l, t, r, b) crop後座標での余白量
    scale_to: tuple              # 最終出力サイズ（規定サイズに一致）
    bg_color: tuple
    fallback: str | None = None  # 比率フォールバックの説明
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def candidate_sizes(cfg: PreflightConfig) -> list:
    sizes = [tuple(s) for s in cfg.sizes]
    if cfg.allow_rotate:
        for w, h in list(sizes):
            if w != h and (h, w) not in sizes:
                sizes.append((h, w))
    return sizes


def analyze(img: Image.Image, trim_threshold: int = 18) -> ImageInfo:
    """内容範囲と背景色を推定する（マージンは足さない素のbbox）。"""
    rgb = img.convert("RGB")
    sample = rgb.resize((1, 1), Image.Resampling.BOX)
    average = sample.getpixel((0, 0))
    corners = [
        rgb.getpixel((0, 0)),
        rgb.getpixel((rgb.width - 1, 0)),
        rgb.getpixel((0, rgb.height - 1)),
        rgb.getpixel((rgb.width - 1, rgb.height - 1)),
    ]
    bg = tuple(int(sum(c[i] for c in corners) / len(corners)) for i in range(3))
    probe = corners + [average]
    detect = tuple(int(sum(c[i] for c in probe) / len(probe)) for i in range(3))
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, detect)).convert("L")
    mask = diff.point(lambda p: 255 if p > trim_threshold else 0)
    bbox = mask.getbbox() or (0, 0, rgb.width, rgb.height)
    return ImageInfo(width=rgb.width, height=rgb.height, content_box=bbox, bg_color=bg)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _horizontal_crop_left(width: int, content_box: tuple, new_w: int) -> int:
    """左右を削る際の左端。内容の水平中心に窓を合わせて画像内にクランプ。"""
    x0, _, x1, _ = content_box
    cx = (x0 + x1) / 2
    return int(round(_clamp(cx - new_w / 2, 0, width - new_w)))


def _vertical_crop_top(height: int, content_box: tuple, new_h: int) -> int:
    """上下を削る際の上端。余白（上→下の順）を先に消費し、
    それでも足りない分は上側の内容へ食い込む（下端の内容を最後まで守る）。"""
    _, y0, _, y1 = content_box
    delta = height - new_h
    cut_top = min(delta, y0)                 # 上の余白
    rem = delta - cut_top
    cut_bottom = min(rem, height - y1)       # 下の余白
    rem -= cut_bottom
    cut_top += rem                           # 食い込みは上側から
    return cut_top


def _split_pad(total: int) -> tuple:
    first = total // 2
    return first, total - first


def plan_normal(info: ImageInfo, cfg: PreflightConfig) -> CropPlan:
    """通常画像（顔アップ・上半身等）: 最近比率を選び、余白(候補1)と最小
    クロップ(候補2)を比較して x スライダー規則で採用を決める。"""
    W, H = info.width, info.height
    r = W / H
    x = _clamp(cfg.pad_crop_x, 0.0, 1.0)

    evaluated = []
    for w, h in candidate_sizes(cfg):
        c = w / h
        if abs(math.log(c / r)) < 1e-9:
            crop_area = pad_area = 0.0
        elif r > c:
            # 横長すぎ: 左右を削る or 上下に余白
            crop_area = (W - H * c) * H
            pad_area = (W / c - H) * W
        else:
            crop_area = W * (H - W / c)
            pad_area = (H * c - W) * H
        evaluated.append(
            {
                "size": (w, h),
                "ratio": c,
                "dist": abs(math.log(c / r)),
                "crop_area": crop_area,
                "pad_area": pad_area,
                "crop_frac": crop_area / (W * H),
            }
        )
    evaluated.sort(key=lambda e: (e["dist"], -e["size"][0] * e["size"][1]))

    def decide_pad(e) -> bool:
        if e["crop_area"] <= 0:
            return False  # 比率一致＝無加工
        return e["crop_area"] >= x * e["pad_area"]

    # 切除率は比率距離の単調関数（crop_frac = 1 - exp(-dist)）なので、
    # 最近比率が常に最小クロップでもある。「削りすぎ」の逃げ先は別比率ではなく
    # 余白側（候補1）に倒すのが唯一の実装（設計書 §3.4）。
    chosen = evaluated[0]
    fallback = None
    use_pad = decide_pad(chosen)
    if not use_pad and chosen["crop_frac"] > cfg.max_crop_frac:
        use_pad = True
        fallback = (
            f"切り取り{chosen['crop_frac']:.0%}が上限{cfg.max_crop_frac:.0%}を超えるため余白で対応"
        )

    w, h = chosen["size"]
    c = w / h
    crop_box = (0, 0, W, H)
    pad = (0, 0, 0, 0)
    if chosen["crop_area"] > 0:
        if use_pad:
            if r > c:
                top, bottom = _split_pad(max(0, int(round(W / c)) - H))
                pad = (0, top, 0, bottom)
            else:
                left, right = _split_pad(max(0, int(round(H * c)) - W))
                pad = (left, 0, right, 0)
        else:
            if r > c:
                new_w = min(W, int(round(H * c)))
                left = _horizontal_crop_left(W, info.content_box, new_w)
                crop_box = (left, 0, left + new_w, H)
            else:
                new_h = min(H, int(round(W / c)))
                top = _vertical_crop_top(H, info.content_box, new_h)
                crop_box = (0, top, W, top + new_h)

    return CropPlan(
        kind="normal",
        src_size=(W, H),
        crop_box=crop_box,
        pad=pad,
        scale_to=(w, h),
        bg_color=info.bg_color,
        fallback=fallback,
        params={
            "padCropX": x,
            "maxCropFrac": cfg.max_crop_frac,
            "usePad": use_pad,
            "cropFrac": round(chosen["crop_frac"], 4),
        },
    )


def plan_fullbody(info: ImageInfo, cfg: PreflightConfig, neck_ratio: float | None = None) -> list:
    """全身絵: 高さを fullbody_base_height に正規化した空間で
    上半身/首から下/足元の正方形3枚＋全身1枚、計4枚の計画を作る。

    実際の切り出しは元画像座標で行う（リサンプリング1回で済み劣化が少ない）。
    正規化空間の長さ L は元画像座標では L/s (s = base_height/H)。
    """
    W, H = info.width, info.height
    x0, y0, x1, y1 = info.content_box
    nr = cfg.neck_ratio if neck_ratio is None else neck_ratio
    s = cfg.fullbody_base_height / H
    tile = cfg.fullbody_tile
    t = min(H, int(round(tile / s)))           # 正方形一辺（元画像座標）
    margin = int(round(cfg.head_margin_px / s))

    # タイル3枚の水平窓: 幅が足りれば内容中心でクロップ、足りなければ余白追加
    if W > t:
        left = _horizontal_crop_left(W, info.content_box, t)
        tile_x = (left, left + t)
        tile_pad = (0, 0)
    else:
        tile_x = (0, W)
        tile_pad = _split_pad(t - W)

    def tile_plan(kind: str, top: float, extra: dict) -> CropPlan:
        top_i = int(round(_clamp(top, 0, H - t)))
        return CropPlan(
            kind=kind,
            src_size=(W, H),
            crop_box=(tile_x[0], top_i, tile_x[1], top_i + t),
            pad=(tile_pad[0], 0, tile_pad[1], 0),
            scale_to=(tile, tile),
            bg_color=info.bg_color,
            params={"baseHeight": cfg.fullbody_base_height, "tile": tile, **extra},
        )

    person_h = max(1, y1 - y0)
    neck_y = y0 + nr * person_h
    plans = [
        tile_plan("fb_upper", y0 - margin, {}),
        tile_plan("fb_body", neck_y, {"neckRatio": nr, "neckY": int(round(neck_y))}),
        tile_plan("fb_feet", min(H, y1 + margin) - t, {}),
    ]

    # 全身1枚: 縦向き候補のうち「人物に食い込まない最も縦長」を選ぶ
    portrait = sorted(
        [size for size in candidate_sizes(cfg) if size[1] >= size[0]],
        key=lambda size: size[1] / size[0],
        reverse=True,
    )
    content_w = max(1, x1 - x0)
    chosen_size = None
    fallback = None
    for w, h in portrait:
        need_w = int(round(H * w / h))
        if need_w >= content_w:
            chosen_size = (w, h)
            break
    if chosen_size is None:
        # 全候補で人物が欠ける: 欠損最小（=最も幅の広い比率）へ逃がす
        chosen_size = min(portrait, key=lambda size: content_w - H * size[0] / size[1])
        fallback = "全候補で横が足りないため、人物の欠損が最小の比率を選択"
    w, h = chosen_size
    need_w = int(round(H * w / h))
    if need_w >= W:
        full_crop = (0, 0, W, H)
        pl, pr = _split_pad(need_w - W)
        full_pad = (pl, 0, pr, 0)
    else:
        # 内容を必ず含む範囲で中心寄せ（余白から先に削られる）
        lo = max(0, min(x1 - need_w, W - need_w))
        hi = max(lo, min(x0, W - need_w))
        left = int(round(_clamp((x0 + x1) / 2 - need_w / 2, lo, hi)))
        full_crop = (left, 0, left + need_w, H)
        full_pad = (0, 0, 0, 0)
    plans.append(
        CropPlan(
            kind="fb_full",
            src_size=(W, H),
            crop_box=full_crop,
            pad=full_pad,
            scale_to=(w, h),
            bg_color=info.bg_color,
            fallback=fallback,
            params={"baseHeight": cfg.fullbody_base_height},
        )
    )
    return plans


def plan_for_mode(info: ImageInfo, cfg: PreflightConfig, mode: str, neck_ratio: float | None = None) -> list:
    if mode == "fullbody":
        return plan_fullbody(info, cfg, neck_ratio=neck_ratio)
    return [plan_normal(info, cfg)]


def apply_plan(img: Image.Image, plan: CropPlan) -> Image.Image:
    """Plan を実行する唯一の関数。出力PNGもサムネも必ずここを通す。"""
    out = img.convert("RGB").crop(plan.crop_box)
    pl, pt, pr, pb = plan.pad
    if pl or pt or pr or pb:
        canvas = Image.new("RGB", (out.width + pl + pr, out.height + pt + pb), plan.bg_color)
        canvas.paste(out, (pl, pt))
        out = canvas
    if (out.width, out.height) != tuple(plan.scale_to):
        out = out.resize(tuple(plan.scale_to), Image.Resampling.LANCZOS)
    return out


def thumbnail(img: Image.Image, plan: CropPlan, max_side: int = 320) -> Image.Image:
    """プレビュー用サムネ = apply_plan の結果の縮小。別経路を作らないこと。"""
    out = apply_plan(img, plan)
    out.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return out

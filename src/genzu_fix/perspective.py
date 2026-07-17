"""画像 → 「アイレベル(地平線)・消失点・キャラクターの垂直線」を引く処理。

レイアウト/原図のパース確認を補助するための注釈を、任意の画像（コンテ/原図のPNG・JPG）
に対して機械的に引く。検出は 3 手法を用意し、同じ画像で精度を比較できる:

  vision  Claude Vision に座標を答えさせる（ラフ線の多いコンテに強い。キャラ識別もできる）
  cv      numpy だけでエッジ→Hough直線→交点クラスタから消失点/アイレベルを幾何的に出す
          （決定的。ただしキャラの識別はできないので「強い垂直線」を返すだけ）
  hybrid  Vision でキャラと大まかな消失点を取り、その近傍の実直線を CV で集めて
          最小二乗で消失点を精密化する（意味理解＋幾何精度のいいとこ取り）

座標は画像サイズに依存しないよう **正規化座標 [0,1]**（x=横/幅, y=縦/高さ）で持つ。
消失点は画角外に出ることがあるので 0..1 を外れた値も許す。

出力:
  <stem>.<method>.png   元画像に線を重ねたオーバーレイ
  <stem>.<method>.json  下記スキーマの座標（正規化）
  <stem>.compare.png    method=all のとき 3 手法の横並び比較（精度を目で比べる用）

JSON スキーマ（正規化座標）:
  {
    "method": "vision" | "cv" | "hybrid",
    "image": {"path": str, "width": int, "height": int},
    "eye_level": {"a": [x, y], "b": [x, y]} | null,   # 2点で引く直線（傾き対応）
    "vanishing_points": [{"x": float, "y": float, "label": str, "axis": str}],
    "characters": [{"name": str, "head": [x, y], "foot": [x, y]}],
    "notes": str
  }

このモジュールはモデル呼び出し（vision）を内蔵するが、ANTHROPIC_API_KEY が無い場合でも
cv だけは動く。conte.py / scene_understanding.py と同じく標準ライブラリで REST を叩く。
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import urllib.request
from dataclasses import dataclass, field, asdict

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Anthropic REST（conte.py と同流儀＝標準ライブラリのみ・要 ANTHROPIC_API_KEY）
DEFAULT_MODEL = "claude-fable-5"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

METHODS = ("vision", "cv", "hybrid")


# ---------------------------------------------------------------------------
# データ構造（座標はすべて正規化 [0,1]。画角外は 0..1 を外れてよい）
# ---------------------------------------------------------------------------
@dataclass
class EyeLevel:
    """アイレベル（地平線）。2 点で持ち、傾いたカメラにも対応する。"""
    a: tuple[float, float]
    b: tuple[float, float]

    @staticmethod
    def horizontal(y: float) -> "EyeLevel":
        return EyeLevel((0.0, y), (1.0, y))

    def to_json(self) -> dict:
        return {"a": [float(self.a[0]), float(self.a[1])],
                "b": [float(self.b[0]), float(self.b[1])]}


@dataclass
class VanishingPoint:
    x: float
    y: float
    label: str = "VP"
    axis: str = "other"   # horizontal / vertical / other

    def to_json(self) -> dict:
        return {"x": float(self.x), "y": float(self.y),
                "label": self.label, "axis": self.axis}


@dataclass
class CharacterVertical:
    name: str
    head: tuple[float, float]
    foot: tuple[float, float]

    def to_json(self) -> dict:
        return {"name": self.name,
                "head": [float(self.head[0]), float(self.head[1])],
                "foot": [float(self.foot[0]), float(self.foot[1])]}


@dataclass
class PerspectiveResult:
    method: str
    width: int
    height: int
    image_path: str = ""
    eye_level: EyeLevel | None = None
    vanishing_points: list[VanishingPoint] = field(default_factory=list)
    characters: list[CharacterVertical] = field(default_factory=list)
    notes: str = ""

    def to_json(self) -> dict:
        return {
            "method": self.method,
            "image": {"path": self.image_path,
                      "width": self.width, "height": self.height},
            "eye_level": self.eye_level.to_json() if self.eye_level else None,
            "vanishing_points": [v.to_json() for v in self.vanishing_points],
            "characters": [c.to_json() for c in self.characters],
            "notes": self.notes,
        }

    @staticmethod
    def from_json(obj: dict) -> "PerspectiveResult":
        img = obj.get("image", {})
        el = obj.get("eye_level")
        return PerspectiveResult(
            method=obj.get("method", ""),
            width=int(img.get("width", 0)),
            height=int(img.get("height", 0)),
            image_path=img.get("path", ""),
            eye_level=EyeLevel(tuple(el["a"]), tuple(el["b"])) if el else None,
            vanishing_points=[VanishingPoint(v["x"], v["y"],
                                             v.get("label", "VP"),
                                             v.get("axis", "other"))
                              for v in obj.get("vanishing_points", [])],
            characters=[CharacterVertical(c["name"], tuple(c["head"]),
                                          tuple(c["foot"]))
                        for c in obj.get("characters", [])],
            notes=obj.get("notes", ""),
        )


# ---------------------------------------------------------------------------
# 幾何ヘルパ（ピクセル座標で計算する。正規化との変換は呼び出し側で）
# ---------------------------------------------------------------------------
def line_from_rho_theta(rho: float, theta: float) -> tuple[float, float, float]:
    """Hough の (rho, theta) → 直線係数 (a, b, c) s.t. a*x + b*y + c = 0, a^2+b^2=1。

    定義: x*cos(theta) + y*sin(theta) = rho。
    縦線(x=const)は theta≈0、横線(y=const)は theta≈±pi/2。
    """
    a, b = math.cos(theta), math.sin(theta)
    return a, b, -rho


def intersect(l1: tuple[float, float, float],
              l2: tuple[float, float, float]) -> tuple[float, float] | None:
    """2 直線 (a,b,c) の交点。平行に近ければ None。"""
    a1, b1, c1 = l1
    a2, b2, c2 = l2
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-9:
        return None
    x = (b1 * c2 - b2 * c1) / det
    y = (a2 * c1 - a1 * c2) / det
    return x, y


def least_squares_vp(lines: list[tuple[float, float, float]]
                     ) -> tuple[float, float] | None:
    """直線群 a*x+b*y+c=0（a^2+b^2=1）に最も近い点 = 消失点を最小二乗で解く。

    各直線への符号付き距離 a*x+b*y+c の二乗和を最小化 → 2x2 正規方程式。
    """
    if len(lines) < 2:
        return None
    A = np.array([[a, b] for a, b, _ in lines], dtype=float)
    d = np.array([-c for _, _, c in lines], dtype=float)
    M = A.T @ A
    if abs(np.linalg.det(M)) < 1e-9:
        return None
    p = np.linalg.solve(M, A.T @ d)
    return float(p[0]), float(p[1])


def point_line_distance(pt: tuple[float, float],
                        line: tuple[float, float, float]) -> float:
    a, b, c = line
    return abs(a * pt[0] + b * pt[1] + c) / math.hypot(a, b)


def _letter(i: int) -> str:
    """0→A, 1→B, ... 25→Z, 26→AA（キャラ/縦線の連番ラベル）。"""
    s, i = "", i + 1
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def estimate_horizon_y(recede: list[tuple[float, float, float, int]],
                       size: tuple[int, int],
                       y_prior: float | None = None,
                       tol: float | None = None) -> float | None:
    """奥行き線の総当たり交点の **y が集中する高さ** = 地平線(アイレベル)を返す。

    透視の核心: 2 点透視でも複数の消失点はすべて同じ地平線（=同じ y）に乗る。
    よって交点の x はばらけても y は地平線に収束する。投票数で重み付けした
    1D ヒストグラムの最頻ビンを取り、その近傍で加重平均して精密化する。
    VP の個数や x から切り離すことで、偽VP・スピード線による傾きを避ける。

    y_prior/tol を与えると（hybrid 用）その近傍の交点だけを使って局所精密化する。
    返値は解析寸ピクセルの y。推定できなければ None。
    """
    w, h = size
    if len(recede) < 2:
        return None
    ys: list[float] = []
    ws: list[float] = []
    for i in range(len(recede)):
        a1, b1, c1, v1 = recede[i]
        for j in range(i + 1, len(recede)):
            a2, b2, c2, v2 = recede[j]
            p = intersect((a1, b1, c1), (a2, b2, c2))
            if p is None:
                continue
            x, y = p
            if not (-1.5 * w <= x <= 2.5 * w and -1.0 * h <= y <= 2.0 * h):
                continue
            if y_prior is not None and tol is not None and abs(y - y_prior) > tol:
                continue
            ys.append(y)
            ws.append(math.sqrt(max(v1, 1) * max(v2, 1)))
    if len(ys) < 2:
        return None
    ya = np.array(ys, dtype=float)
    wa = np.array(ws, dtype=float)
    binw = max(h / 40.0, 1.0)
    lo = float(ya.min())
    nb = max(1, int((ya.max() - lo) / binw) + 1)
    idx = np.clip(((ya - lo) / binw).astype(int), 0, nb - 1)
    hist = np.zeros(nb)
    np.add.at(hist, idx, wa)
    peak = int(hist.argmax())
    sel = (idx >= peak - 1) & (idx <= peak + 1)
    if wa[sel].sum() <= 0:
        return float(np.average(ya, weights=wa))
    return float(np.average(ya[sel], weights=wa[sel]))


def _snap_horizontal(eye: "EyeLevel | None",
                     threshold_deg: float = 4.0) -> "EyeLevel | None":
    """ほぼ水平なアイレベルは水平に丸める（アニメ背景はロール無しが既定）。"""
    if eye is None:
        return None
    (ax, ay), (bx, by) = eye.a, eye.b
    dx, dy = bx - ax, by - ay
    if abs(dx) < 1e-9:
        return eye
    if abs(math.degrees(math.atan2(dy, dx))) <= threshold_deg:
        return EyeLevel.horizontal((ay + by) / 2.0)
    return eye


# ---------------------------------------------------------------------------
# 入出力ヘルパ
# ---------------------------------------------------------------------------
def _media_type(path: str) -> str:
    p = path.lower()
    if p.endswith(".png"):
        return "image/png"
    if p.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if p.endswith(".webp"):
        return "image/webp"
    if p.endswith(".gif"):
        return "image/gif"
    return "image/png"


def _norm(pt, w, h):
    return (pt[0] / w, pt[1] / h)


def _denorm(pt, w, h):
    return (pt[0] * w, pt[1] * h)


# ---------------------------------------------------------------------------
# CV 検出（numpy のみ）: エッジ → Hough → 交点クラスタ → 消失点/アイレベル
# ---------------------------------------------------------------------------
def _load_gray(path: str, max_dim: int = 1100) -> tuple[np.ndarray, float]:
    """グレースケール配列と、元寸 → 解析寸の縮小率 scale を返す。"""
    im = Image.open(path).convert("L")
    w, h = im.size
    scale = min(1.0, max_dim / max(w, h))
    if scale < 1.0:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    return np.asarray(im, dtype=np.float64), scale


def _edge_points(gray: np.ndarray, keep_frac: float = 0.08,
                 max_points: int = 6000) -> tuple[np.ndarray, np.ndarray]:
    """Sobel 勾配強度の上位 keep_frac をエッジ点として返す（x, y 配列）。"""
    gx = np.zeros_like(gray)
    gy = np.zeros_like(gray)
    # Sobel
    k = gray
    gx[:, 1:-1] = (k[:, 2:] - k[:, :-2])
    gy[1:-1, :] = (k[2:, :] - k[:-2, :])
    mag = np.hypot(gx, gy)
    if mag.max() <= 0:
        return np.empty(0), np.empty(0)
    thr = np.quantile(mag, 1.0 - keep_frac)
    ys, xs = np.nonzero(mag >= max(thr, 1e-6))
    if len(xs) > max_points:
        idx = np.linspace(0, len(xs) - 1, max_points).astype(int)
        xs, ys = xs[idx], ys[idx]
    return xs.astype(np.float64), ys.astype(np.float64)


def _hough_lines(xs: np.ndarray, ys: np.ndarray, shape: tuple[int, int],
                 n_lines: int = 60, theta_step_deg: float = 1.0
                 ) -> list[tuple[float, float, float]]:
    """エッジ点から Hough 累積を作り、非極大抑制で上位 n_lines を返す。

    各要素 (rho, theta, votes)。
    """
    h, w = shape
    if len(xs) == 0:
        return []
    thetas = np.deg2rad(np.arange(-90.0, 90.0, theta_step_deg))
    cos_t, sin_t = np.cos(thetas), np.sin(thetas)
    diag = math.hypot(w, h)
    rho_res = 2.0
    n_rho = int(2 * diag / rho_res) + 1
    rho0 = diag
    # rho = x cos + y sin（点 x bins スパース化済み）
    rho = xs[:, None] * cos_t[None, :] + ys[:, None] * sin_t[None, :]
    rbin = np.clip(((rho + rho0) / rho_res).astype(int), 0, n_rho - 1)
    acc = np.zeros((n_rho, len(thetas)), dtype=np.int32)
    for j in range(len(thetas)):
        np.add.at(acc[:, j], rbin[:, j], 1)
    # 非極大抑制つき peak 取り
    peaks = []
    work = acc.copy()
    vote_min = max(int(0.10 * work.max()), 8)
    nms_r, nms_t = 12, 3
    for _ in range(n_lines):
        idx = int(work.argmax())
        ri, ti = divmod(idx, work.shape[1])
        v = work[ri, ti]
        if v < vote_min:
            break
        rho_val = ri * rho_res - rho0
        peaks.append((rho_val, float(thetas[ti]), int(v)))
        r0, r1 = max(0, ri - nms_r), min(n_rho, ri + nms_r + 1)
        t0, t1 = max(0, ti - nms_t), min(len(thetas), ti + nms_t + 1)
        work[r0:r1, t0:t1] = 0
    return peaks


def detect_cv(path: str, max_dim: int = 1100) -> PerspectiveResult:
    """numpy だけで消失点・アイレベル・強い垂直線を出す（決定的）。"""
    gray, scale = _load_gray(path, max_dim)
    h, w = gray.shape
    W, H = Image.open(path).size  # 元寸
    res = PerspectiveResult("cv", W, H, image_path=os.path.abspath(path))

    xs, ys = _edge_points(gray)
    peaks = _hough_lines(xs, ys, (h, w))
    if not peaks:
        res.notes = "直線が検出できませんでした（コントラスト不足の可能性）。"
        return res

    # 角度で分類: theta≈0 → 縦線, theta≈±90 → 横線, それ以外 → 奥行き線
    vert, recede = [], []
    for rho, theta, v in peaks:
        deg = math.degrees(theta)
        a, b, c = line_from_rho_theta(rho, theta)
        if abs(deg) < 8:                       # ほぼ縦線
            vert.append((rho, theta, v, (a, b, c)))
        elif abs(abs(deg) - 90) < 8:           # ほぼ横線 → 消失点推定に使うと無限遠なので除外
            continue
        else:
            recede.append((a, b, c, v))

    # 消失点: 奥行き線の総当たり交点を 2D ヒストでクラスタ → 上位を VP に
    vp_px = _cluster_vanishing_points(recede, (w, h), max_vps=2)
    for i, (vx, vy, weight) in enumerate(vp_px):
        nx, ny = _norm((vx / scale, vy / scale), W, H)
        res.vanishing_points.append(
            VanishingPoint(nx, ny, label=f"VP{i+1}", axis="other"))

    # アイレベル(地平線)は VP の x/個数から切り離し、奥行き線交点の y が
    # 集中する高さで水平に引く（2点透視でも複数VPは同じ地平線=同じyに乗る）。
    hy = estimate_horizon_y(recede, (w, h))
    if hy is None and vp_px:
        hy = vp_px[0][1]
    if hy is not None:
        res.eye_level = EyeLevel.horizontal((hy / scale) / H)

    # キャラ垂直線: CV では人物を識別できないので「強い縦線」を最大3本返す
    vert.sort(key=lambda t: t[2], reverse=True)
    for i, (rho, theta, v, (a, b, c)) in enumerate(vert[:3]):
        # 縦線 x ≈ rho/cos(theta)。画像上端〜下端を head/foot 代わりに使う
        if abs(a) < 1e-6:
            continue
        x_top = (-c - b * 0) / a
        x_bot = (-c - b * h) / a
        head = _norm((x_top / scale, 0.0), W, H)
        foot = _norm((x_bot / scale, H), W, H)
        res.characters.append(
            CharacterVertical(name=f"縦線{_letter(i)}", head=head, foot=foot))

    res.notes = (f"CV: lines={len(peaks)} recede={len(recede)} "
                 f"vert={len(vert)} vps={len(vp_px)} horizon_y={'有' if hy else '無'}. "
                 f"※CVは人物識別不可のため characters は強い縦線(縦線A/B/C)です。")
    return res


def _cluster_vanishing_points(recede: list[tuple[float, float, float, int]],
                              size: tuple[int, int], max_vps: int = 2
                              ) -> list[tuple[float, float, float]]:
    """奥行き線の交点を集め、2D グリッドで密なクラスタを VP として返す。

    返値 (x, y, weight)（解析寸ピクセル）。画角の ±1.5 倍までを採用範囲にする。
    """
    w, h = size
    if len(recede) < 2:
        return []
    pts = []
    for i in range(len(recede)):
        a1, b1, c1, v1 = recede[i]
        for j in range(i + 1, len(recede)):
            a2, b2, c2, v2 = recede[j]
            p = intersect((a1, b1, c1), (a2, b2, c2))
            if p is None:
                continue
            x, y = p
            if -1.5 * w <= x <= 2.5 * w and -1.5 * h <= y <= 2.5 * h:
                pts.append((x, y, math.sqrt(v1 * v2)))
    if not pts:
        return []
    arr = np.array(pts, dtype=float)
    # グリッド集計（セル = 画角の 1/20）。重みは投票数の幾何平均。
    cell = max(w, h) / 20.0
    keys = {}
    for x, y, wgt in pts:
        k = (int(x // cell), int(y // cell))
        keys.setdefault(k, []).append((x, y, wgt))
    clusters = []
    for k, members in keys.items():
        m = np.array(members)
        wsum = m[:, 2].sum()
        cx = (m[:, 0] * m[:, 2]).sum() / wsum
        cy = (m[:, 1] * m[:, 2]).sum() / wsum
        clusters.append((cx, cy, wsum * len(members)))  # 票数×支持線数
    clusters.sort(key=lambda t: t[2], reverse=True)
    # 第2以降の VP は「主消失点に対し十分な支持がある」ものだけ採用する。
    # こうしないと 1 点透視の離散化ノイズを 2 点目に拾い、アイレベルが傾く。
    SECOND_VP_RATIO = 0.5
    out: list[tuple[float, float, float]] = []
    for cx, cy, score in clusters:
        if out and score < out[0][2] * SECOND_VP_RATIO:
            break
        if any(math.hypot(cx - ox, cy - oy) < cell * 3 for ox, oy, _ in out):
            continue
        out.append((cx, cy, score))
        if len(out) >= max_vps:
            break
    return out


# ---------------------------------------------------------------------------
# Vision 検出（Claude REST）
# ---------------------------------------------------------------------------
VISION_SYSTEM = (
    "あなたはアニメのレイアウト/背景原図のパース（透視図法）を読む専門家です。"
    "渡された1枚の画像について、(1)アイレベル(地平線/カメラの目線の高さ)、"
    "(2)消失点(透視線が集まる点。画角の外でもよい)、"
    "(3)各キャラクターの『立ちの垂直軸』(足元の接地点と頭頂)を読み取り、"
    "すべて正規化座標で返します。"
)

VISION_PROMPT = (
    "この画像のパースを解析し、次の JSON だけを出力してください（前後に説明文を書かない）。\n"
    "座標は必ず正規化: x=左0..右1, y=上0..下1。消失点は画角外なら 0..1 を外れた値で構いません。\n"
    "アイレベルは透視の収束高さに置く一本の直線で、left(x=0付近)とright(x=1付近)の2点で表す。"
    "カメラが意図的に傾いて(ダッチアングル)いない限り水平＝両点の y を同じにすること。\n"
    "キャラクターは画面内の人物ごとに1つ。head=頭頂、foot=足元の接地点。"
    "name は画面左から順に『人物A』『人物B』…で構わない。人物がいなければ空配列。\n"
    "消失点は確信のあるものだけ（無ければ空配列）。\n\n"
    "{\n"
    '  "eye_level": {"a": [x, y], "b": [x, y]},\n'
    '  "vanishing_points": [{"x": x, "y": y, "label": "VP1", "axis": "horizontal|vertical|other"}],\n'
    '  "characters": [{"name": "人物1", "head": [x, y], "foot": [x, y]}],\n'
    '  "notes": "読み取りの根拠を1〜2行"\n'
    "}"
)


def _anthropic_vision(path: str, model: str, api_key: str,
                      max_tokens: int = 2048) -> dict:
    """画像 1 枚を Claude に渡し、生 JSON(dict) を返す。"""
    with open(path, "rb") as fh:
        b64 = base64.standard_b64encode(fh.read()).decode("ascii")
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": VISION_SYSTEM,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64",
                            "media_type": _media_type(path), "data": b64}},
                {"type": "text", "text": VISION_PROMPT},
            ],
        }],
    }
    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = "".join(b.get("text", "") for b in data.get("content", [])
                   if b.get("type") == "text")
    return _parse_json_object(text)


def _parse_json_object(text: str) -> dict:
    """応答テキストから最初の JSON オブジェクトを頑健に取り出す。"""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    raw = m.group(1) if m else text
    start = raw.find("{")
    if start < 0:
        return {}
    depth, end = 0, None
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        return {}
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return {}


def _result_from_vision_obj(obj: dict, path: str, method: str = "vision"
                            ) -> PerspectiveResult:
    W, H = Image.open(path).size
    res = PerspectiveResult(method, W, H, image_path=os.path.abspath(path))
    el = obj.get("eye_level")
    if el and "a" in el and "b" in el:
        # ほぼ水平なら水平に丸める（ロール無し前提でブレを抑える）
        res.eye_level = _snap_horizontal(EyeLevel(tuple(el["a"]), tuple(el["b"])))
    for v in obj.get("vanishing_points", []) or []:
        if "x" in v and "y" in v:
            res.vanishing_points.append(
                VanishingPoint(float(v["x"]), float(v["y"]),
                               v.get("label", "VP"), v.get("axis", "other")))
    # キャラ名は当てにならない（Vision の推測が外れる）ので 人物A/B/C に固定する。
    ci = 0
    for c in obj.get("characters", []) or []:
        if "head" in c and "foot" in c:
            res.characters.append(
                CharacterVertical(f"人物{_letter(ci)}",
                                  tuple(c["head"]), tuple(c["foot"])))
            ci += 1
    res.notes = obj.get("notes", "")
    return res


def detect_vision(path: str, model: str = DEFAULT_MODEL,
                  api_key: str | None = None) -> PerspectiveResult:
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY が未設定です（vision/hybrid に必要）。")
    obj = _anthropic_vision(path, model, api_key)
    return _result_from_vision_obj(obj, path, "vision")


# ---------------------------------------------------------------------------
# Hybrid: Vision のキャラ＋大まかな VP を、CV の実直線で最小二乗精密化
# ---------------------------------------------------------------------------
def detect_hybrid(path: str, model: str = DEFAULT_MODEL,
                  api_key: str | None = None,
                  max_dim: int = 1100) -> PerspectiveResult:
    vis = detect_vision(path, model=model, api_key=api_key)
    W, H = vis.width, vis.height
    res = PerspectiveResult("hybrid", W, H, image_path=os.path.abspath(path))
    res.characters = vis.characters   # キャラは Vision の意味理解をそのまま採用

    # CV の実直線を集める
    gray, scale = _load_gray(path, max_dim)
    h, w = gray.shape
    xs, ys = _edge_points(gray)
    peaks = _hough_lines(xs, ys, (h, w))
    recede = []  # (a, b, c, votes)
    for rho, theta, v in peaks:
        deg = math.degrees(theta)
        if abs(deg) < 8 or abs(abs(deg) - 90) < 8:
            continue
        a, b, c = line_from_rho_theta(rho, theta)
        recede.append((a, b, c, v))

    refined: list[VanishingPoint] = []
    seeds = vis.vanishing_points or []
    used_notes = []
    for vp in seeds:
        seed_px = (vp.x * W * scale, vp.y * H * scale)  # 解析寸ピクセル
        near = [ln for ln in recede
                if point_line_distance(seed_px, ln[:3]) < 0.12 * max(w, h)]
        if len(near) >= 3:
            p = least_squares_vp([ln[:3] for ln in near])
            if p is not None and -3 * w <= p[0] <= 4 * w and -3 * h <= p[1] <= 4 * h:
                nx, ny = _norm((p[0] / scale, p[1] / scale), W, H)
                refined.append(VanishingPoint(nx, ny, vp.label, vp.axis))
                used_notes.append(f"{vp.label}: {len(near)}線で精密化")
                continue
        refined.append(vp)  # 近傍線が足りなければ Vision の値を維持
        used_notes.append(f"{vp.label}: Vision値を維持")

    # Vision が VP を出さなかったときは CV 単独で補う
    if not refined:
        cvp = _cluster_vanishing_points(recede, (w, h), max_vps=2)
        for i, (vx, vy, _) in enumerate(cvp):
            nx, ny = _norm((vx / scale, vy / scale), W, H)
            refined.append(VanishingPoint(nx, ny, f"VP{i+1}", "other"))
        if cvp:
            used_notes.append(f"Vision無し→CVで{len(cvp)}点補完")

    res.vanishing_points = refined

    # アイレベル: Vision の地平線高さを事前分布に、その近傍の交点 y で精密化（水平で出す）。
    # VP の x/個数や傾きには依存させない（偽VP・スピード線による傾きを避ける）。
    prior_y = None
    if vis.eye_level:
        prior_y = ((vis.eye_level.a[1] + vis.eye_level.b[1]) / 2.0) * H * scale
    hy = estimate_horizon_y(recede, (w, h), y_prior=prior_y,
                            tol=(0.12 * h if prior_y is not None else None))
    if hy is not None:
        res.eye_level = EyeLevel.horizontal((hy / scale) / H)
        used_notes.append("アイレベル: Vision近傍の交点yで精密化(水平)")
    elif vis.eye_level:
        res.eye_level = _snap_horizontal(vis.eye_level)
        used_notes.append("アイレベル: Vision値を採用(水平化)")
    else:
        hy2 = estimate_horizon_y(recede, (w, h))
        if hy2 is not None:
            res.eye_level = EyeLevel.horizontal((hy2 / scale) / H)
            used_notes.append("アイレベル: CV交点yのみ")

    res.notes = "Hybrid: " + "; ".join(used_notes) if used_notes else \
        "Hybrid: 精密化対象なし（Vision値を使用）"
    return res


def detect(method: str, path: str, model: str = DEFAULT_MODEL,
           api_key: str | None = None) -> PerspectiveResult:
    if method == "cv":
        return detect_cv(path)
    if method == "vision":
        return detect_vision(path, model=model, api_key=api_key)
    if method == "hybrid":
        return detect_hybrid(path, model=model, api_key=api_key)
    raise ValueError(f"未知の method: {method}（{METHODS} のいずれか）")


# ---------------------------------------------------------------------------
# 描画（PIL オーバーレイ）
# ---------------------------------------------------------------------------
COL_EYE = (0, 200, 255)        # アイレベル: シアン
COL_VP = (255, 40, 200)        # 消失点: マゼンタ
COL_VERT = (40, 220, 70)       # キャラ垂直線(真の鉛直): 緑
COL_AXIS = (255, 160, 0)       # キャラ実軸(頭→足): オレンジ
COL_GUIDE = (255, 120, 210)    # 消失点へのガイド線: 薄マゼンタ


# ラベルに日本語（役名等）が来るので CJK 対応フォントを優先する。Linux/Windows 両対応。
_FONT_CANDIDATES = (
    # Linux（このリポジトリの web セッション環境）
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    # Windows（黒江さんのローカル実行環境）
    r"C:\Windows\Fonts\meiryo.ttc",
    r"C:\Windows\Fonts\YuGothM.ttc",
    r"C:\Windows\Fonts\msgothic.ttc",
    # 最後の砦（日本語は豆腐になるが描画は動く）
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _clip_line_to_box(p, q, w, h):
    """線分 p-q を [0,w]x[0,h] でクリップ（Liang-Barsky）。外なら None。"""
    x0, y0 = p
    x1, y1 = q
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x0 - 0), (dx, w - x0), (-dy, y0 - 0), (dy, h - y0)):
        if abs(pp) < 1e-12:
            if qq < 0:
                return None
            continue
        r = qq / pp
        if pp < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
    if t0 > t1:
        return None
    return ((x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy))


def _fan_segments(vx, vy, W, H, density):
    """消失点 (vx,vy) から画像矩形を覆う扇状ガイド線分を density 本返す（エディタと同形）。

    消失点が画角内なら全方位、画角外なら画像が張る角度範囲(コーン)に density 本。
    """
    inside = 0 <= vx <= W and 0 <= vy <= H
    if inside:
        amin, amax = 0.0, 2 * math.pi
    else:
        angs = [math.atan2(cy - vy, cx - vx)
                for cx, cy in ((0, 0), (W, 0), (W, H), (0, H))]
        amin, amax = min(angs), max(angs)
        if amax - amin > math.pi:           # 角度の巻き込みを補正
            angs = [a + 2 * math.pi if a < 0 else a for a in angs]
            amin, amax = min(angs), max(angs)
    big = (W + H) * 3
    n = max(1, int(density))
    segs = []
    for k in range(n + 1):
        a = amin + (amax - amin) * k / n
        seg = _clip_line_to_box((vx, vy),
                                (vx + math.cos(a) * big, vy + math.sin(a) * big), W, H)
        if seg:
            segs.append(seg)
    return segs


def _dashed_line(draw, p, q, color, width=2, dash=14, gap=9):
    x0, y0 = p
    x1, y1 = q
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1:
        return
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    d = 0.0
    while d < length:
        a = (x0 + ux * d, y0 + uy * d)
        b = (x0 + ux * min(d + dash, length), y0 + uy * min(d + dash, length))
        draw.line([a, b], fill=color, width=width)
        d += dash + gap


def render(res: PerspectiveResult, src_path: str, out_path: str,
           title: str | None = None, line_scale: float = 1.0,
           guides: int = 14) -> str:
    """検出結果を元画像に重ねて PNG 保存。out_path を返す。

    生成の参照資料・指示に使うので線は太め。line_scale で太さ、guides で
    消失点ごとのパースガイド本数（エディタの「ガイド密度」と同じ）を指定する。
    """
    base = Image.open(src_path).convert("RGB")
    W, H = base.size
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(over)
    fs = max(16, int(min(W, H) * 0.026 * max(0.6, line_scale)))
    font = _font(fs)
    lw = max(3, int(min(W, H) * 0.0048 * line_scale))   # 主要線（太め）
    gw = max(2, int(lw * 0.55))                          # ガイド線

    def P(pt):  # 正規化 → ピクセル
        return (pt[0] * W, pt[1] * H)

    # --- 消失点へのガイド線（扇状・密度=guides、薄く先に。0=扇なし） + 消失点マーカー
    if guides > 0:
        for vp in res.vanishing_points:
            vx, vy = P((vp.x, vp.y))
            for seg in _fan_segments(vx, vy, W, H, guides):
                draw.line(seg, fill=COL_GUIDE + (110,), width=gw)

    # --- アイレベル（地平線）
    if res.eye_level:
        a = P(res.eye_level.a)
        b = P(res.eye_level.b)
        # 直線を画面全幅へ延長
        if abs(b[0] - a[0]) > 1e-6:
            slope = (b[1] - a[1]) / (b[0] - a[0])
            a = (0.0, a[1] - slope * a[0])
            b = (float(W), a[1] + slope * W)
        seg = _clip_line_to_box(a, b, W, H)
        if seg:
            draw.line(seg, fill=COL_EYE + (255,), width=lw)
            ty = min(max(seg[0][1] + 4, 2), H - fs - 2)
            _text(draw, (8, ty), "EYE LEVEL / アイレベル", font, COL_EYE)

    # --- 消失点マーカー（画角外はクランプして矢印表示）
    for vp in res.vanishing_points:
        vx, vy = P((vp.x, vp.y))
        inside = 0 <= vx <= W and 0 <= vy <= H
        mx, my = min(max(vx, 12), W - 12), min(max(vy, 12), H - 12)
        r = max(7, int(min(W, H) * 0.012))
        draw.line([(mx - r, my), (mx + r, my)], fill=COL_VP + (255,), width=lw)
        draw.line([(mx, my - r), (mx, my + r)], fill=COL_VP + (255,), width=lw)
        draw.ellipse([mx - r, my - r, mx + r, my + r],
                     outline=COL_VP + (255,), width=lw)
        lab = vp.label + ("" if inside else " (画角外)")
        _text(draw, (mx + r + 3, my - fs), lab, font, COL_VP)

    # --- キャラクターの垂直線
    for ch in res.characters:
        hx, hy = P(ch.head)
        fx, fy = P(ch.foot)
        # 真の鉛直線（足元接地点を通る）= 緑。少し上下に延ばす
        top_y = min(hy, fy) - (abs(fy - hy) * 0.12 + 6)
        bot_y = max(hy, fy) + 6
        seg = _clip_line_to_box((fx, top_y), (fx, bot_y), W, H)
        if seg:
            draw.line(seg, fill=COL_VERT + (255,), width=lw)
        # 実際の体軸（頭→足）= オレンジ破線（鉛直からの傾きが見える）
        _dashed_line(draw, (hx, hy), (fx, fy), COL_AXIS + (255,),
                     width=max(2, lw - 1))
        # 頭・足のドット
        dr = max(5, int(min(W, H) * 0.008 * line_scale))
        draw.ellipse([hx - dr, hy - dr, hx + dr, hy + dr], fill=COL_AXIS + (255,))
        draw.ellipse([fx - dr, fy - dr, fx + dr, fy + dr], fill=COL_VERT + (255,))
        _text(draw, (fx + dr + 2, hy - fs), ch.name, font, COL_VERT)

    out = Image.alpha_composite(base.convert("RGBA"), over).convert("RGB")

    # タイトル帯
    if title:
        draw2 = ImageDraw.Draw(out)
        bar_h = fs + 10
        draw2.rectangle([0, 0, W, bar_h], fill=(20, 20, 20))
        _text(draw2, (8, 5), title, font, (255, 255, 255), bg=None)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    out.save(out_path)
    return out_path


def _text(draw, xy, s, font, color, bg=(0, 0, 0)):
    """縁取り付きテキスト（背景に負けないよう黒縁を回す）。"""
    x, y = xy
    if bg is not None:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    draw.text((x + dx, y + dy), s, font=font, fill=bg)
    draw.text((x, y), s, font=font, fill=color)


def render_comparison(results: list[tuple[str, PerspectiveResult]],
                      src_path: str, out_path: str,
                      tmp_dir: str | None = None) -> str:
    """複数手法のオーバーレイを横並びにした比較画像を作る。"""
    tiles = []
    tmp_dir = tmp_dir or os.path.dirname(out_path) or "."
    for method, res in results:
        tp = os.path.join(tmp_dir, f"_cmp_{method}.png")
        render(res, src_path, tp, title=f"{method.upper()}")
        tiles.append(Image.open(tp).convert("RGB"))
    if not tiles:
        raise ValueError("比較対象がありません。")
    target_h = min(t.height for t in tiles)
    resized = [t.resize((int(t.width * target_h / t.height), target_h))
               for t in tiles]
    pad = 8
    total_w = sum(t.width for t in resized) + pad * (len(resized) + 1)
    canvas = Image.new("RGB", (total_w, target_h + pad * 2), (40, 40, 40))
    x = pad
    for t in resized:
        canvas.paste(t, (x, pad))
        x += t.width + pad
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    canvas.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# 高レベル API
# ---------------------------------------------------------------------------
def annotate(path: str, methods: list[str], out_dir: str | None = None,
             model: str = DEFAULT_MODEL, api_key: str | None = None
             ) -> dict[str, dict]:
    """画像に対し指定手法で検出→オーバーレイPNG＋JSONを書き出す。

    返値: {method: {"json": path, "png": path, "result": PerspectiveResult, "error": str?}}
    methods に複数あれば compare.png も作る。
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    out_dir = out_dir or os.path.join("work", "_perspective", stem)
    os.makedirs(out_dir, exist_ok=True)

    outputs: dict[str, dict] = {}
    ok_results: list[tuple[str, PerspectiveResult]] = []
    for m in methods:
        try:
            res = detect(m, path, model=model, api_key=api_key)
        except Exception as e:
            outputs[m] = {"error": str(e)}
            print(f"  ! {m}: {e}")
            continue
        json_path = os.path.join(out_dir, f"{stem}.{m}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(res.to_json(), f, ensure_ascii=False, indent=2)
        png_path = os.path.join(out_dir, f"{stem}.{m}.png")
        render(res, path, png_path, title=m.upper())
        outputs[m] = {"json": json_path, "png": png_path, "result": res}
        ok_results.append((m, res))
        print(f"  {m}: VP={len(res.vanishing_points)} "
              f"chars={len(res.characters)} "
              f"eye={'有' if res.eye_level else '無'}  -> {png_path}")

    if len(ok_results) >= 2:
        cmp_path = os.path.join(out_dir, f"{stem}.compare.png")
        render_comparison(ok_results, path, cmp_path, tmp_dir=out_dir)
        outputs["_compare"] = {"png": cmp_path}
        print(f"  compare: {cmp_path}")

    return outputs


# ---------------------------------------------------------------------------
# CLI（python -m genzu_fix.perspective <image> --method all）
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="genzu_fix.perspective",
        description="画像にアイレベル・消失点・キャラ垂直線を引く（vision/cv/hybrid）")
    p.add_argument("image", help="入力画像（PNG/JPG など）")
    p.add_argument("--method", default="all",
                   help="vision | cv | hybrid | all（複数はカンマ区切り可）")
    p.add_argument("--out-dir", default=None,
                   help="出力先（既定 work/_perspective/<stem>）")
    p.add_argument("--model", default=DEFAULT_MODEL, help="vision/hybrid のモデル")
    a = p.parse_args(argv)

    if not os.path.isfile(a.image):
        print(f"画像が見つかりません: {a.image}")
        return 1
    if a.method == "all":
        methods = list(METHODS)
    else:
        methods = [m.strip() for m in a.method.split(",") if m.strip()]
    bad = [m for m in methods if m not in METHODS]
    if bad:
        print(f"未知の method: {bad}（{METHODS} のいずれか）")
        return 1

    print(f"image  : {a.image}")
    print(f"methods: {methods}")
    outputs = annotate(a.image, methods, out_dir=a.out_dir, model=a.model)
    ok = [m for m in methods if "result" in outputs.get(m, {})]
    if not ok:
        print("\nすべての手法が失敗しました。")
        return 1
    print("\n完了。PNG/JSON は上記パス。method=all なら compare.png を Read で見比べてください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

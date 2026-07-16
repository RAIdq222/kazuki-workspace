"""GKV など担当別カットを一括処理するバッチドライバ（ローカルCLI実行用）。

カット→美術ボード対応CSV(runs/cut_board_map_ep7.csv)を読み、指定担当(既定 GKV)の
原図を1本ずつ次の流れで処理する:

  1. prep   : PSD → 表示合成PNG(文字除外) → ヘッダー除去 → GPT出力寸ぴったりの入力PNG
  2. 生成    : 公式 Higgsfield CLI を呼ぶ
                 higgsfield upload <input.png>            → media UUID
                 higgsfield generate create gpt_image_2 \
                     --prompt ... --aspect_ratio <ar> --resolution 2k --quality high \
                     <IMAGE_FLAG> <uuid> --wait --json     → 結果URL
                 結果PNGをダウンロード
  3. finish : 生成結果を原図画角へ戻し、元PSDへ「AI原図修正」レイヤー差し込み、台帳追記

注意:
- 入力画像を渡すフラグ名はCLIバージョンで違うため --image-flag で変更可（既定 --image）。
  必ず一度 `higgsfield generate create gpt_image_2 --help` で確認すること。
- まず --dry-run で「prepだけ実行＋叩くhiggsfieldコマンドを表示」して確認するのを推奨。
- プロンプトは genzu_fix.prompt（GLOBAL/SCENE/CUT の3層アセンブリ）に委譲する。色は参照しない。
- 束カット(016_026 等)は同じPSD=同じ原図なので、ファイル単位で1回だけ生成する。
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

from . import image_aspect, psd_export, frame, ledger, qc, prompt as promptlib


def build_prompt(board: str, scene: str, prompt_override: str | None = None,
                 registry=None, cut: str = "") -> str:
    """カット別 EN プロンプト（GPT Image 2 入力用）を返す。

    層構造の組み立ては genzu_fix.prompt（3層アセンブリ）に委譲する。
    JP（確認用）も併せて欲しい場合は build_prompt_pair を使う。
    """
    if prompt_override:
        return prompt_override
    return promptlib.build(board, scene, registry=registry, cut=cut).en


def build_prompt_pair(board: str, scene: str, prompt_override: str | None = None,
                      registry=None, cut: str = "", cut_info_map=None) -> tuple[str, str | None]:
    """(EN, JP) を返す。EN はモデル入力、JP は人の確認用。
    cut_info_map があり当該カットの充足済み行が在れば situation/remove 込みで組む。
    prompt_override がある場合は (override, None)。"""
    if prompt_override:
        return prompt_override, None
    p = promptlib.build_for_cut(cut, board, scene, registry=registry, cut_info_map=cut_info_map)
    return p.en, p.jp


def _resolve(cmd: list[str]) -> list[str]:
    """Windowsでnpm製CLI(higgsfield.cmd)を確実に起動できるよう実体パスに解決する。
    .cmd/.bat は cmd /c 経由で起動（CreateProcessが直接実行できないため）。"""
    import shutil
    exe = shutil.which(cmd[0])
    if not exe:
        # PATHEXTで拾えない場合のフォールバック
        for ext in (".cmd", ".exe", ".bat", ""):
            cand = shutil.which(cmd[0] + ext)
            if cand:
                exe = cand
                break
    if not exe:
        raise RuntimeError(
            f"'{cmd[0]}' が見つかりません。Higgsfield CLI が入っているか確認してください "
            f"(`higgsfield auth token` が通るか)。")
    if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", exe] + cmd[1:]
    return [exe] + cmd[1:]


def _run(cmd: list[str], dry: bool, timeout: int = 900) -> str:
    print("    $ " + " ".join(cmd))
    if dry:
        return ""
    # - stdin=DEVNULL: CLIが対話入力（ログイン確認等）を求めても永久に待たず、即エラーで返す
    # - timeout: ハングを打ち切る。Windowsのnpm系CLIは .cmd ラッパの下に node の孫プロセスが
    #   いるため、親だけ kill するとパイプが閉じず communicate が解けない → taskkill /T で子孫ごと止める
    proc = subprocess.Popen(_resolve(cmd), stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8")
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True)
        else:
            proc.kill()
        try:
            proc.communicate(timeout=10)
        except Exception:  # noqa 後始末失敗でも本体のエラーを優先
            pass
        raise RuntimeError(f"command timed out after {timeout}s: {' '.join(cmd[:3])}…")
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {((err or out) or '').strip()[:400]}")
    return (out or "").strip()


def _run_retry(cmd: list[str], dry: bool, timeout: int = 900, tries: int = 3) -> str:
    """_run に一時エラー(HTTP 5xx)のリトライを足したもの。それ以外のエラーは即時raise。"""
    for attempt in range(tries):
        try:
            return _run(cmd, dry, timeout=timeout)
        except RuntimeError as e:
            if attempt + 1 < tries and re.search(r"HTTP 5\d\d", str(e)):
                wait = 8 * (attempt + 1)
                print(f"    [retry] 一時エラー、{wait}s後に再試行 {attempt + 1}/{tries - 1}: {str(e)[:100]}")
                time.sleep(wait)
                continue
            raise
    return ""  # 到達しない


def _hf_upload(path: str, dry: bool) -> str:
    """higgsfield upload create <path> → media UUID（--json 優先、無ければ出力からUUID抽出）。"""
    out = _run_retry(["higgsfield", "upload", "create", path, "--json"], dry)
    if dry or not out:
        return "<uuid>"
    try:
        data = json.loads(out)
        for k in ("id", "media_id", "uuid", "mediaId"):
            if isinstance(data, dict) and data.get(k):
                return data[k]
    except json.JSONDecodeError:
        pass
    m = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", out)
    if m:
        return m.group(0)
    raise RuntimeError(f"uploadのUUIDを取得できませんでした: {out[:200]}")


def _find_result_url(out: str) -> str | None:
    """CLI出力（JSON or テキスト）から結果画像URLを探す。無ければ None。"""
    if not out:
        return None

    # JSON構造はバージョン差があるため複数候補を探索
    def find_url(o):
        if isinstance(o, str) and re.match(r"https?://.*\.(png|webp|jpg)", o):
            return o
        if isinstance(o, dict):
            for v in o.values():
                u = find_url(v)
                if u:
                    return u
        if isinstance(o, list):
            for v in o:
                u = find_url(v)
                if u:
                    return u
        return None
    try:
        return find_url(json.loads(out))
    except json.JSONDecodeError:
        m = re.search(r"https?://\S+\.(?:png|webp|jpg)", out)
        return m.group(0) if m else None


_UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


def _hf_generate(media_id: str, prompt: str, aspect: str, resolution: str,
                 quality: str, model: str, image_flag: str, dry: bool,
                 extra_images: list[str] | None = None) -> str:
    """generate create → 結果画像URL。extra_images は追加の参照画像(UUID/パス)。

    CLIの世代差に両対応する:
      旧: create --wait が完了まで待って結果URL入りJSONを返す
      新: create はジョブIDを即返す → `generate wait <job_id>` で完了を待って結果を取る
    """
    # 改行はCLIに渡す前に畳む。Windowsではコマンドライン中の改行で引数列が分断され、
    # 改行以降（プロンプト残り・--aspect_ratio・--image・--wait）が全て失われる
    # （実測: ジョブに prompt=1行目のみ / medias=[] / aspect_ratio=既定 で記録されていた）。
    prompt = re.sub(r"\s*\n+\s*", " ", prompt or "").strip()
    # create は待たずにジョブIDだけ受け取り、完了待ちは自前ループで行う。
    # （create --wait はポーリング中の一時エラー(HTTP 502等)で即死し、走っている
    #   リモートジョブを失敗扱いにしてしまう。ID さえあれば待ち直しは何度でも安全）
    cmd = ["higgsfield", "generate", "create", model,
           "--prompt", prompt, "--aspect_ratio", aspect,
           "--resolution", resolution, "--quality", quality,
           image_flag, media_id]
    for ex in (extra_images or []):
        cmd += [image_flag, ex]
    cmd += ["--json"]
    out = _run_retry(cmd, dry)
    if dry:
        return ""
    url = _find_result_url(out)
    m = re.search(_UUID_RE, out or "")
    if not url and not m:
        raise RuntimeError(f"生成結果URLもジョブIDも取得できませんでした: {(out or '')[:200]}")
    job_id = m.group(0) if m else ""

    # 完了待ち: wait → get を一時エラーに耐えながら繰り返す（予算 ~13分）
    deadline = time.time() + 780
    last_err = ""
    while not url and time.time() < deadline:
        try:
            out = _run(["higgsfield", "generate", "wait", job_id, "--json"], dry, timeout=300)
            url = _find_result_url(out)
        except RuntimeError as e:  # 502等の一時エラー/タイムアウト → get で状態確認して継続
            last_err = str(e)
        if url:
            break
        try:
            got = json.loads(_run(["higgsfield", "generate", "get", job_id, "--json"],
                                  dry, timeout=120))
            status = (got.get("status") or "").lower()
            url = _find_result_url(json.dumps(got))
            if url:
                break
            if status in ("failed", "canceled", "cancelled", "error"):
                raise RuntimeError(f"ジョブ {job_id} が失敗しました: {str(got)[:200]}")
            print(f"    [wait] ジョブ {job_id[:8]}… status={status or '?'} 待機継続"
                  + (f"（直前: {last_err[:80]}）" if last_err else ""))
        except RuntimeError as e:
            if "が失敗しました" in str(e):
                raise
            last_err = str(e)  # get 自体の一時エラーも継続
        except json.JSONDecodeError:
            pass
        time.sleep(10)
    if not url:
        raise RuntimeError(f"ジョブ {job_id} の結果を取得できませんでした: {last_err[:200]}")

    # パラメータがジョブに正しく載ったかの事後検証（黙って捨てられる事故を早期検知）
    if job_id:
        try:
            got = json.loads(_run(["higgsfield", "generate", "get", job_id, "--json"],
                                  dry, timeout=120))
            p = got.get("params") or {}
            want_medias = 1 + len(extra_images or [])
            n_medias = len(p.get("medias") or [])
            if n_medias < want_medias:
                print(f"    [warn] 参照画像がジョブに {n_medias}/{want_medias} 枚しか載っていません")
            if p.get("aspect_ratio") and p["aspect_ratio"] != aspect:
                print(f"    [warn] aspect_ratio がジョブに反映されていません: {p['aspect_ratio']} (指定 {aspect})")
        except Exception:  # noqa 検証失敗は本体を止めない
            pass
    return url


def _trim_border(im):
    """ボード外周の黒/単色フチ（PSDキャンバスの余白）を落とし、絵の領域だけにする。"""
    from PIL import Image, ImageChops
    bg = Image.new("RGB", im.size, im.getpixel((2, 2)))
    bbox = ImageChops.difference(im, bg).getbbox()
    return im.crop(bbox) if bbox else im


def _prep_board(src: str, out: str, maxside: int = 1536, mode: str = "patches"):
    """美術ボードを参照入力用に加工する。

    mode="patches"（既定）: 拡大ディテールを3枚切り出して横タイルにする。
      断片には部屋全体の構図が無い＝構図の乗っ取りが起きない。タッチ・線密度・
      材質・空気感だけを運ぶ（全景参照が原図の構図に勝つ事故はSP2 c005で2回実測）。
    mode="full": 全景をそのまま縮小（明示オプトイン時のみ）。
    """
    from PIL import Image
    im = _trim_border(Image.open(src).convert("RGB"))
    if mode == "full":
        if max(im.size) > maxside:
            s = maxside / max(im.size)
            im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        im.save(out)
        return out
    w, h = im.size
    side = max(64, min(w, h) // 2)   # 元の1/2角＝タッチが読める拡大率
    anchors = [(0.08, 0.30), (0.38, 0.48), (0.60, 0.12)]  # 左中/中央下/右上（重なりにくい散らし）
    P, M = 512, 24
    canvas = Image.new("RGB", (P * 3 + M * 4, P + M * 2), (255, 255, 255))
    for i, (fx, fy) in enumerate(anchors):
        x = max(0, min(int(w * fx), w - side))
        y = max(0, min(int(h * fy), h - side))
        patch = im.crop((x, y, x + side, y + side)).resize((P, P), Image.LANCZOS)
        canvas.paste(patch, (M + i * (P + M), M))
    canvas.save(out)
    return out
    return out


def process_cut(psd_path: str, board: str, scene: str, out_dir: str,
                prompt_override: str | None, resolution: str, quality: str,
                model: str, image_flag: str, dry: bool, include_book: bool = False,
                header_top: int | None = None, board_path: str | None = None,
                genzu_source: str = "base", cut_num: str = "",
                cut_info_map=None, qc_vision: bool = False,
                genzu_layers=None, board_mode: str = "patches") -> dict:
    os.makedirs(out_dir, exist_ok=True)
    cut = os.path.splitext(os.path.basename(psd_path))[0]
    visible = os.path.join(out_dir, "visible.png")
    body = os.path.join(out_dir, "body.png")
    inp = os.path.join(out_dir, "input.png")
    # 1. prep（原図ソース: base=背景自動検出 / visible=見たまま / override=手動レイヤー選択）
    if genzu_source == "visible":
        vw, vh = psd_export.export_visible_to_png(psd_path, visible, bg=(255, 255, 255),
                                                  drop_text=False)
        linfo = {"strategy": "visible", "layers": ["(見たまま)"]}
    elif genzu_source == "override" and genzu_layers:
        names = set(genzu_layers)
        allnames = [li.name for li in psd_export.list_layers(psd_path)]
        vw, vh = psd_export.export_with_overrides(
            psd_path, visible, show=names, hide={n for n in allnames if n not in names},
            bg=(255, 255, 255))
        linfo = {"strategy": "override", "layers": list(genzu_layers)}
    else:
        vw, vh, linfo = psd_export.export_background_layer(
            psd_path, visible, bg=(255, 255, 255), include_book=include_book)
    # 既定は「切らない」＝原図全域を入力に（レジストは入力=出力グリッドで担保, §20.6）。
    # ヘッダーはプロンプトで除去。header_top 指定時のみ帯を落とす（非標準シート用）。
    if header_top is None:
        region = (0, 0, vw, vh)
        body = visible
    else:
        region = frame.strip_header(visible, body, top_override=header_top)
    prep = image_aspect.build_input_image(body, inp, resolution=resolution)
    use_board = bool(board_path)
    # プロンプトは genzu_fix.prompt（3層）に委譲。EN=モデル入力 / JP=確認用を出力先へ残す。
    prompt, prompt_jp = build_prompt_pair(board, scene, prompt_override,
                                          cut=cut_num, cut_info_map=cut_info_map)
    if use_board and board_mode != "full":
        # 既定: ボードは「ディテール断片」で渡す（構図が存在しない＝乗っ取り不能。
        # 全景渡しは[IMAGES]宣言でも原図の構図に勝つことをSP2 c005で2回実測）。
        prompt += (
            "\n\n[IMAGES] Two images are attached. IMAGE 1 is the rough layout (genzu) for THIS cut:"
            " its composition, camera angle, framing and content are the ground truth — redraw exactly"
            " this view and nothing else. IMAGE 2 shows magnified DETAIL FRAGMENTS cropped from the"
            " art-setting board of the same location: use them ONLY as the authority for drawing touch,"
            " line density, materials and mood. They are fragments, not a composition — the full view of"
            " this shot is defined solely by IMAGE 1.")
        if prompt_jp:
            prompt_jp += (
                "\n\n[画像] 1枚目=このカットの原図（構図・画角・内容の正。この画角だけを描き直す）。"
                "2枚目=同じ場所の美術ボードの拡大ディテール断片（タッチ・線密度・材質・空気感の根拠として"
                "のみ使う。断片であり構図ではない。このカットの画角は1枚目だけが定義する）。")
    elif use_board:
        # 全景オプトイン時の役割宣言
        prompt += (
            "\n\n[IMAGES] Two images are attached. IMAGE 1 is the rough layout (genzu) for THIS cut:"
            " its composition, camera angle, framing and content are the ground truth — redraw exactly"
            " this view and nothing else. IMAGE 2 is an art-setting board of the same location,"
            " for reference ONLY: use it to understand the room's structure, furniture, materials and"
            " the intended line density, but do NOT copy its camera, framing or composition, and do NOT"
            " add elements from it that lie outside IMAGE 1's view. If the two disagree about what is"
            " visible in this shot, IMAGE 1 wins.")
        if prompt_jp:
            prompt_jp += (
                "\n\n[画像] 1枚目=このカットの原図（構図・画角・内容の正。この画角だけを描き直す）。"
                "2枚目=同じ場所の美術ボード（空間構造・什器・線の密度の参考のみ。"
                "構図や画角は写さない。1枚目の画角外の要素は足さない。食い違う時は1枚目が正）。")
    with open(os.path.join(out_dir, "prompt.en.txt"), "w", encoding="utf-8") as f:
        f.write(prompt)
    if prompt_jp:
        with open(os.path.join(out_dir, "prompt.jp.txt"), "w", encoding="utf-8") as f:
            f.write(prompt_jp)
    print(f"    layer[{linfo['strategy']}]={linfo['layers']}  "
          f"crop={'no' if header_top is None else header_top}  "
          f"board_img={board_mode if use_board else 'no'}  "
          f"input {prep.canvas_w}x{prep.canvas_h} ({prep.aspect_ratio})")
    # 2. 生成（Higgsfield CLI）。gpt_image_2 の --image はパス可（MODELS.md）。
    gen_raw = os.path.join(out_dir, "gen_raw.png")
    uuid = _hf_upload(inp, dry)
    extra = []
    if use_board:
        board_ref = (_prep_board(board_path, os.path.join(out_dir, "board_ref.png"),
                                 mode=board_mode)
                     if not dry else board_path)
        extra.append(_hf_upload(board_ref, dry))
    url = _hf_generate(uuid, prompt, prep.aspect_ratio, resolution, quality, model,
                       image_flag, dry, extra)
    if not dry:
        # timeout 付きDL（ハングでスレッド/バッチが永久 running 化するのを防ぐ）
        with urllib.request.urlopen(url, timeout=300) as r, open(gen_raw, "wb") as f:
            f.write(r.read())
    # 3. finish（戻し→region復帰→PSD差し込み）
    out_psd = os.path.join(out_dir, f"{cut}_AI.psd")
    if not dry:
        restored = os.path.join(out_dir, "restored.png")
        full = os.path.join(out_dir, "restored_full.png")
        image_aspect.restore_output_image(gen_raw, restored, prep)
        frame.paste_into_region((vw, vh), tuple(region), restored, full)
        layer = psd_export.insert_result_layer(psd_path, full, out_psd, base_name="AI原図修正")
        # 検品(QC): プログラム判定は常時（空白/破綻・色残り）。視覚判定は qc_vision 時のみ。
        qc_dict = {}
        try:
            vv = None
            if qc_vision and os.environ.get("ANTHROPIC_API_KEY"):
                vv = qc.vision_check(visible, full)
            qc_dict = qc.asdict(qc.evaluate(full, vision_verdicts=vv))
            with open(os.path.join(out_dir, "qc.json"), "w", encoding="utf-8") as f:
                json.dump(qc_dict, f, ensure_ascii=False)
            print(f"    qc[{qc_dict.get('verdict')}] {qc_dict.get('reasons')}")
        except Exception as e:  # noqa QCで生成自体を失敗にしない
            print(f"    qc skip: {str(e)[:120]}")
        rec = ledger.GenRecord(
            run_id="", created_at=time.time(), cut=cut, genzu_file=psd_path,
            board_files=[board] if board else [], model=model,
            params={"aspect_ratio": prep.aspect_ratio, "resolution": resolution, "quality": quality},
            prompt=prompt, result_url=url, output_file=out_psd, status="completed",
            qc=qc_dict, notes="batch local-CLI", scene_info={"scene": scene, "board": board})
        # 台帳は出力ルート側（work/非git）へ。git管理の runs/ledger.jsonl に直接追記しない
        # （毎回dirty・複数マシンで衝突するため）。run_dir = <out>/<cut> の親 = <out>。
        ledger.append(rec, os.path.join(os.path.dirname(os.path.normpath(out_dir)), "ledger.jsonl"))
        print(f"    -> {out_psd}  layer='{layer}'")
    return {"cut": cut, "psd": out_psd, "url": url}


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="genzu_fix.batch",
                                description="担当別カットを一括生成（ローカルCLI / Higgsfield）")
    p.add_argument("--csv", default="runs/cut_board_map_ep7.csv", help="カット→ボード対応CSV")
    p.add_argument("--genzu-dir", required=True, help="原図PSDが置いてあるローカルディレクトリ（再帰探索）")
    p.add_argument("--out", default="work/batch", help="出力ルート")
    p.add_argument("--assignee", default="GKV", help="処理する担当（既定 GKV）")
    p.add_argument("--prompts-dir", default=None, help="任意。<cut>.txt があればプロンプトを上書き")
    p.add_argument("--limit", type=int, default=None, help="先頭N本だけ処理（試運転用）")
    p.add_argument("--resolution", default="2k")
    p.add_argument("--quality", default="high")
    p.add_argument("--model", default="gpt_image_2")
    p.add_argument("--image-flag", default="--image",
                   help="生成時に入力画像UUIDを渡すフラグ名（要 `higgsfield generate create gpt_image_2 --help` で確認）")
    p.add_argument("--dry-run", action="store_true", help="prepのみ実行し、叩くhiggsfieldコマンドを表示")
    p.add_argument("--include-book", action="store_true",
                   help="BOOK◯（燭台/寝台/柱/モヤ等の別ブック）も合成に含める（既定は除外）")
    p.add_argument("--header-top", type=int, default=None,
                   help="ヘッダー帯の下端yを指定して切る（既定は切らない＝原図全域を入力）")
    p.add_argument("--boards-dir", default=None,
                   help="美術ボード画像のあるディレクトリ（再帰探索）。指定すると2枚目入力に渡す")
    p.add_argument("--cut-info", default="runs/cut_scene_info_ep7.csv",
                   help="カット別構造化情報CSV（situation/remove 込み）。在ればプロンプトに反映")
    p.add_argument("--qc-vision", action="store_true",
                   help="生成後にAI視覚QCも実行（要 ANTHROPIC_API_KEY）")
    a = p.parse_args(argv)

    # 美術ボード画像の索引（ファイル名→パス）
    board_index = {}
    if a.boards_dir:
        for root, _, files in os.walk(a.boards_dir):
            for f in files:
                board_index.setdefault(f, os.path.join(root, f))

    # カット別 situation/remove（conte 由来）を読み込み（無ければ空でフォールバック）
    cut_info_map = promptlib.load_cut_info(a.cut_info)
    if cut_info_map:
        print(f"cut_scene_info: {len(cut_info_map)} カット読み込み（{a.cut_info}）")

    # PSDの実パスを genzu-dir 配下から探す索引（ファイル名→パス）
    index = {}
    for root, _, files in os.walk(a.genzu_dir):
        for f in files:
            if f.lower().endswith(".psd"):
                index.setdefault(f, os.path.join(root, f))

    with open(a.csv, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get("assignee") == a.assignee]

    # ファイル単位に集約（束カットの二重生成を防ぐ）
    seen, jobs = set(), []
    for r in rows:
        fn = r["filename"]
        if fn in seen:
            continue
        seen.add(fn)
        jobs.append(r)
    if a.limit:
        jobs = jobs[:a.limit]

    print(f"対象担当={a.assignee} / 対象ファイル {len(jobs)}本"
          + (f"（先頭{a.limit}本）" if a.limit else "")
          + (" [DRY-RUN]" if a.dry_run else ""))
    ok, miss, err = 0, [], []
    for i, r in enumerate(jobs, 1):
        fn = r["filename"]
        psd = index.get(fn)
        print(f"[{i}/{len(jobs)}] cut {r['cut']}  {fn}")
        if not psd:
            print("    ! 原図PSDが genzu-dir に見つかりません（スキップ）")
            miss.append(fn)
            continue
        prompt_override = None
        if a.prompts_dir:
            pf = os.path.join(a.prompts_dir, f"{r['cut']}.txt")
            if os.path.exists(pf):
                prompt_override = open(pf, encoding="utf-8").read().strip()
        out_dir = os.path.join(a.out, os.path.splitext(fn)[0])
        board_name = r.get("board", "")
        board_path = board_index.get(board_name) if (a.boards_dir and board_name) else None
        if a.boards_dir and board_name and not board_path:
            print(f"    （注: 美術ボード '{board_name}' が boards-dir に見つからずテキスト参照のみ）")
        try:
            process_cut(psd, board_name, r.get("scene", ""), out_dir,
                        prompt_override, a.resolution, a.quality, a.model, a.image_flag,
                        a.dry_run, a.include_book, a.header_top, board_path,
                        cut_num=r.get("cut", ""), cut_info_map=cut_info_map,
                        qc_vision=a.qc_vision)
            ok += 1
        except Exception as e:
            print(f"    ! 失敗: {e}")
            err.append((fn, str(e)))
    print(f"\n完了 {ok}/{len(jobs)} ・ 原図見つからず {len(miss)} ・ 失敗 {len(err)}")
    if miss:
        print("  見つからず:", ", ".join(miss))
    if err:
        for fn, e in err:
            print(f"  失敗 {fn}: {e[:120]}")


if __name__ == "__main__":
    main()

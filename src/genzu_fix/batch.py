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
- 美術ボードは v1 ではプロンプト文（場所/時間/構成物の手掛かり）として参照する。色は参照しない。
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

from . import image_aspect, psd_export, frame, ledger


# 美術ボード/シーン名から場面ヒント（時代・場所・時間）を抽出してプロンプトへ。
def _scene_hint(board: str, scene: str) -> str:
    b = os.path.splitext(board)[0] if board else ""
    parts = []
    if scene:
        parts.append(re.sub(r"c\d.*$", "", scene))  # "森_夜c053～206" -> "森_夜"
    if b:
        parts.append(b)
    return " / ".join(p for p in parts if p)


def build_prompt(board: str, scene: str, prompt_override: str | None = None) -> str:
    if prompt_override:
        return prompt_override
    hint = _scene_hint(board, scene)
    ctx = (f" Scene/era reference (from the assigned art board — match its period, "
           f"architecture and structural elements, NOT its color): {hint}." if hint else "")
    return (
        "Redraw this rough background layout sheet as a CLEAN black-and-white line "
        "drawing for anime art (haikei genzu). KEEP REGISTRATION: keep the EXACT same "
        "framing, composition, position and scale as the input — every structure must "
        "stay where it is; do not zoom, pan, shift, or re-center. Output: monochrome ink "
        "line art only, no color, no grey fills, hand-drawn line quality. Colored areas in "
        "the input are placeholder fills — render them as plain line art, not color. Remove "
        "all production marks, handwritten notes, labels and tap holes, and remove any "
        "character/figure and the things they carry or wear; reconstruct the plain "
        "environment behind them (keep furniture and fixtures that belong to the room)." +
        ctx +
        " The blank margin bands are padding — leave them blank, do not extend artwork into them."
    )


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


def _run(cmd: list[str], dry: bool) -> str:
    print("    $ " + " ".join(cmd))
    if dry:
        return ""
    r = subprocess.run(_resolve(cmd), capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"command failed ({r.returncode}): {(r.stderr or r.stdout).strip()[:400]}")
    return r.stdout.strip()


def _hf_upload(path: str, dry: bool) -> str:
    """higgsfield upload <path> → media UUID（--json 優先、無ければ出力からUUID抽出）。"""
    out = _run(["higgsfield", "upload", path, "--json"], dry)
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


def _hf_generate(media_id: str, prompt: str, aspect: str, resolution: str,
                 quality: str, model: str, image_flag: str, dry: bool) -> str:
    """generate create → 結果画像URL。"""
    cmd = ["higgsfield", "generate", "create", model,
           "--prompt", prompt, "--aspect_ratio", aspect,
           "--resolution", resolution, "--quality", quality,
           image_flag, media_id, "--wait", "--json"]
    out = _run(cmd, dry)
    if dry or not out:
        return ""
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        m = re.search(r"https?://\S+\.(?:png|webp|jpg)", out)
        if m:
            return m.group(0)
        raise RuntimeError(f"生成結果URLを取得できませんでした: {out[:200]}")
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
    url = find_url(data)
    if not url:
        raise RuntimeError(f"JSONから結果URLが見つかりません: {out[:200]}")
    return url


def process_cut(psd_path: str, board: str, scene: str, out_dir: str,
                prompt_override: str | None, resolution: str, quality: str,
                model: str, image_flag: str, dry: bool) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    cut = os.path.splitext(os.path.basename(psd_path))[0]
    visible = os.path.join(out_dir, "visible.png")
    body = os.path.join(out_dir, "body.png")
    inp = os.path.join(out_dir, "input.png")
    # 1. prep
    vw, vh = psd_export.export_visible_to_png(psd_path, visible, bg=(255, 255, 255), drop_text=True)
    region = frame.strip_header(visible, body)
    prep = image_aspect.build_input_image(body, inp, resolution=resolution)
    prompt = build_prompt(board, scene, prompt_override)
    print(f"    input {prep.canvas_w}x{prep.canvas_h} ({prep.aspect_ratio})  board='{board or '—'}'")
    # 2. 生成（Higgsfield CLI）
    gen_raw = os.path.join(out_dir, "gen_raw.png")
    uuid = _hf_upload(inp, dry)
    url = _hf_generate(uuid, prompt, prep.aspect_ratio, resolution, quality, model, image_flag, dry)
    if not dry:
        urllib.request.urlretrieve(url, gen_raw)
    # 3. finish（戻し→region復帰→PSD差し込み）
    out_psd = os.path.join(out_dir, f"{cut}_AI.psd")
    if not dry:
        restored = os.path.join(out_dir, "restored.png")
        full = os.path.join(out_dir, "restored_full.png")
        image_aspect.restore_output_image(gen_raw, restored, prep)
        frame.paste_into_region((vw, vh), tuple(region), restored, full)
        layer = psd_export.insert_result_layer(psd_path, full, out_psd, base_name="AI原図修正")
        rec = ledger.GenRecord(
            run_id="", created_at=time.time(), cut=cut, genzu_file=psd_path,
            board_files=[board] if board else [], model=model,
            params={"aspect_ratio": prep.aspect_ratio, "resolution": resolution, "quality": quality},
            prompt=prompt, result_url=url, output_file=out_psd, status="completed",
            notes="batch local-CLI", scene_info={"scene": scene, "board": board})
        ledger.append(rec)
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
    a = p.parse_args(argv)

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
        try:
            process_cut(psd, r.get("board", ""), r.get("scene", ""), out_dir,
                        prompt_override, a.resolution, a.quality, a.model, a.image_flag, a.dry_run)
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

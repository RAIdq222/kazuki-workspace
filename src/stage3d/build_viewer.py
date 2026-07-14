# -*- coding: utf-8 -*-
"""3Dステージの単一HTMLビューワーを生成する。

.blend → GLB(メッシュのみ) → Three.js アプリ(esbuildでバンドル)と共に
1つのHTMLへ埋め込む。出来たHTMLはブラウザで開くだけで動く(ネット接続不要)。

前提: npm i three esbuild 済みの node_modules があること (--node_dir で指定)。

実行例:
    python3 src/stage3d/build_viewer.py \
        --blend work/kitchen_stage.blend \
        --title "尚善 台所 3Dステージ" \
        --node_dir /path/to/dir_with_node_modules \
        --out work/kitchen_viewer.html
"""
import argparse
import base64
import html
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>html,body{{margin:0;height:100%;overflow:hidden;background:#17120d}}canvas{{display:block}}</style>
</head>
<body>
<script>window.__VIEWER_CFG={cfg_json};window.__GLB_B64="{glb_b64}";</script>
<script>{bundle}</script>
</body>
</html>
"""

# 旧・台所ステージ互換のデフォルト設定
DEFAULT_CFG = {
    "exposure": 1.0,
    "background": "#17120d",
    "presets": {
        "A": {"pos": [5.55, 1.40, -0.55], "tgt": [1.35, 1.15, -4.05], "label": "かまど側"},
        "B": {"pos": [0.75, 1.45, -3.75], "tgt": [5.90, 1.05, -1.35], "label": "入口側"},
        "T": {"pos": [3.20, 7.20, 2.80], "tgt": [3.20, 0.30, -2.20], "label": "俯瞰"},
    },
    "lights": [
        {"type": "hemi", "sky": "#fff1dd", "ground": "#2e2418", "i": 0.35},
        {"type": "point", "p": [3.9, 1.7, -4.1], "c": "#fff2d8", "i": 9, "shadow": True},
        {"type": "point", "p": [0.3, 1.7, -1.55], "c": "#fff2d8", "i": 9, "shadow": True},
        {"type": "point", "p": [2.2, 1.7, -0.3], "c": "#fff2d8", "i": 7, "shadow": True},
        {"type": "point", "p": [1.8, 2.3, -2.2], "c": "#ffdfb0", "i": 5},
        {"type": "point", "p": [4.6, 2.3, -2.2], "c": "#ffdfb0", "i": 5},
    ],
}


def export_glb(blend_path, glb_path, exclude_prefixes=()):
    import bpy
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend_path))
    for o in list(bpy.data.objects):
        if o.type != "MESH" or any(o.name.startswith(p) for p in exclude_prefixes):
            bpy.data.objects.remove(o)
    # Base Color にノードが刺さっているマテリアル(床の色ムラ等)は glTF に変換できず
    # 白になってしまうため、リンクを外して固定色に落とす
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if not bsdf:
            continue
        base = bsdf.inputs["Base Color"]
        if base.is_linked:
            for link in list(base.links):
                m.node_tree.links.remove(link)
            if m.name.startswith("m_floor"):
                base.default_value = (0.19, 0.12, 0.07, 1.0)
    bpy.ops.export_scene.gltf(filepath=os.path.abspath(glb_path), export_format="GLB",
                              export_apply=True, export_lights=False, export_cameras=False)


def bundle_js(node_dir):
    # esbuild はエントリファイルの位置から node_modules を解決するため、
    # エントリを node_dir 側へコピーしてからバンドルする。
    import shutil
    esbuild = os.path.join(node_dir, "node_modules", ".bin", "esbuild")
    entry = os.path.join(node_dir, "_viewer_app_entry.js")
    shutil.copyfile(os.path.join(HERE, "viewer_app.js"), entry)
    try:
        out = subprocess.run(
            [esbuild, entry, "--bundle", "--minify", "--format=iife", "--target=es2020"],
            capture_output=True, text=True, cwd=node_dir, check=True)
    finally:
        os.remove(entry)
    return out.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--title", default="3Dステージ ビューワー")
    ap.add_argument("--node_dir", required=True, help="node_modules(three, esbuild)があるディレクトリ")
    ap.add_argument("--out", required=True)
    ap.add_argument("--glb", default="", help="既存GLBを使う場合(省略時はblendから書き出し)")
    ap.add_argument("--config", default="", help="シーン設定JSON (presets/lights/fog等)。省略時は台所用デフォルト")
    ap.add_argument("--exclude_prefix", action="append", default=[],
                    help="GLBから除外するオブジェクト名の接頭辞 (例: fog_)")
    args = ap.parse_args()

    import json
    cfg = dict(DEFAULT_CFG)
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfg = json.load(f)
    cfg["title"] = args.title

    glb = args.glb or (os.path.splitext(args.out)[0] + ".glb")
    if not args.glb:
        export_glb(args.blend, glb, tuple(args.exclude_prefix))
    with open(glb, "rb") as f:
        glb_b64 = base64.b64encode(f.read()).decode()
    bundle = bundle_js(args.node_dir)
    page = TEMPLATE.format(title=html.escape(args.title),
                           cfg_json=json.dumps(cfg, ensure_ascii=False), glb_b64=glb_b64, bundle=bundle)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(page)
    print("wrote", args.out, f"({os.path.getsize(args.out)/1e6:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())

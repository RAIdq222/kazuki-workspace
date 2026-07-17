"""パース編集エディタ（ブラウザ上のキャンバス・アプリ）。

背景の絵が「キャラから想定されるアイレベル/パース」と食い違うことがあるため、
自動検出だけでは決め切れない。人がアイレベル・消失点を置く（または自動推定を叩き台に
微調整する）と、消失点へ収束するパース・ガイドを自動で引くエディタ。

- 画像ファイルのパスを入れて「開く」→ 画像を表示
- アイレベル（地平線）と消失点をドラッグで配置 → パース線（扇状ガイド）を自動描画
- 1点透視〜2点透視、さらに消失点を増やせる（ジブリ背景のような複数消失点にも対応）
- 鉛直の消失点（3点透視）と、人物の垂直線も置ける
- 「自動推定」で cv / vision / hybrid（perspective.py）を呼び、結果を初期値として流し込む
- 「保存」で正規化座標 JSON ＋ オーバーレイ PNG を書き出す（perspective.render を再利用）

起動:
    pip install flask
    python run_perspective_editor.py            # ランチャ（PYTHONPATH不要）
    # or
    PYTHONPATH=src python -m genzu_fix.perspective_editor --port 8770 [--image path]

座標はすべて正規化 [0,1]（x=横/幅, y=縦/高さ）で持ち、perspective.py の JSON と相互運用する。
"""
from __future__ import annotations

import argparse
import json
import os

from PIL import Image

from . import perspective


CONFIG = {"image": ""}


def _ok(path: str) -> bool:
    return bool(path) and os.path.isfile(path)


def _img_info(path: str) -> dict:
    with Image.open(path) as im:
        w, h = im.size
    return {"ok": True, "path": os.path.abspath(path),
            "name": os.path.basename(path), "width": w, "height": h}


def create_app():
    from flask import Flask, jsonify, request, send_file, Response
    app = Flask(__name__)

    @app.get("/")
    def index():
        return Response(PAGE, mimetype="text/html")

    @app.get("/api/config")
    def api_config():
        return jsonify({"image": CONFIG.get("image", "")})

    @app.get("/api/open")
    def api_open():
        path = request.args.get("path", "").strip().strip('"')
        if not _ok(path):
            return jsonify({"error": f"画像が見つかりません: {path}"}), 404
        try:
            return jsonify(_img_info(path))
        except Exception as e:
            return jsonify({"error": f"画像を開けません: {e}"}), 400

    @app.post("/api/render")
    def api_render():
        """注釈を元画像にフルレゾで焼いた PNG を返す（ブラウザでダウンロード保存する用）。"""
        import io
        import tempfile
        b = request.json or {}
        path = (b.get("path") or "").strip().strip('"')
        ann = b.get("annotation") or {}
        if not _ok(path):
            return jsonify({"error": "画像が見つかりません"}), 404
        line_scale = float(b.get("line_scale", 1.0) or 1.0)
        guides = int(b.get("guides", 14) or 14)
        try:
            res = perspective.PerspectiveResult.from_json(ann)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                tmp = tf.name
            perspective.render(res, path, tmp, title=None,
                               line_scale=line_scale, guides=guides)
            with open(tmp, "rb") as fh:
                data = fh.read()
            os.remove(tmp)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        stem = os.path.splitext(os.path.basename(path))[0]
        from flask import Response as _Resp
        return _Resp(data, mimetype="image/png", headers={
            "Content-Disposition": f'attachment; filename="{stem}.perspective.png"'})

    @app.post("/api/upload")
    def api_upload():
        """ドラッグ&ドロップ等のファイルを受け取り work/_uploads に保存してパスを返す。"""
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"error": "ファイルがありません"}), 400
        name = os.path.basename(f.filename)
        up_dir = os.path.join("work", "_uploads")
        os.makedirs(up_dir, exist_ok=True)
        dst = os.path.join(up_dir, name)
        f.save(dst)
        try:
            return jsonify(_img_info(dst))
        except Exception as e:
            return jsonify({"error": f"画像を開けません: {e}"}), 400

    @app.get("/image")
    def image():
        path = request.args.get("path", "").strip().strip('"')
        if not _ok(path):
            return jsonify({"error": "not found"}), 404
        return send_file(os.path.abspath(path))

    @app.post("/api/detect")
    def api_detect():
        b = request.json or {}
        path = (b.get("path") or "").strip().strip('"')
        method = b.get("method", "cv")
        if not _ok(path):
            return jsonify({"error": "画像が見つかりません"}), 404
        if method not in perspective.METHODS:
            return jsonify({"error": f"未知の method: {method}"}), 400
        try:
            res = perspective.detect(method, path)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        return jsonify(res.to_json())

    return app


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="genzu_fix.perspective_editor",
        description="パース編集エディタ（ブラウザ）")
    p.add_argument("--port", type=int, default=8770)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--image", default="", help="起動時に開く画像（任意）")
    a = p.parse_args(argv)
    CONFIG["image"] = os.path.abspath(a.image) if a.image else ""
    app = create_app()
    url = f"http://{a.host}:{a.port}/"
    print(f"パース編集エディタ: {url}")
    if CONFIG["image"]:
        print(f"  起動時に開く: {CONFIG['image']}")
    print("  ブラウザで開いて、画像パスを入れて『開く』。Ctrl+C で終了。")
    app.run(host=a.host, port=a.port, debug=False, threaded=True)
    return 0


# ---------------------------------------------------------------------------
# フロントエンド（1ファイル・キャンバス）。座標は正規化 [0,1]。
# ---------------------------------------------------------------------------
PAGE = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>パース編集エディタ</title>
<style>
  :root{--bg:#1e1f24;--panel:#26282f;--ink:#e8e8ea;--muted:#9aa0aa;--line:#3a3d46;
        --eye:#00c8ff;--vp:#ff28c8;--vpv:#ffb400;--vert:#28dc46;--axis:#ffa000;--guide:#ff78d2;}
  *{box-sizing:border-box}
  body{margin:0;font:13px/1.5 system-ui,'Segoe UI',sans-serif;background:var(--bg);color:var(--ink);}
  header{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:8px 10px;background:var(--panel);border-bottom:1px solid var(--line);}
  header .grp{display:flex;gap:6px;align-items:center;padding-right:10px;border-right:1px solid var(--line);}
  header .grp:last-child{border-right:none}
  input[type=text]{background:#15161a;border:1px solid var(--line);color:var(--ink);border-radius:6px;padding:6px 8px;min-width:320px}
  button,select{background:#33363f;border:1px solid var(--line);color:var(--ink);border-radius:6px;padding:6px 10px;cursor:pointer}
  button:hover{background:#3d414b}
  button.pri{background:#2563eb;border-color:#2563eb}
  button.warn{background:#7a2230;border-color:#7a2230}
  label.chk{display:flex;gap:5px;align-items:center;color:var(--muted);cursor:pointer}
  .legend{display:flex;gap:12px;color:var(--muted);font-size:12px;flex-wrap:wrap}
  .legend i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:4px}
  #wrap{position:relative;width:100vw;height:calc(100vh - 96px);}
  #cv{display:block;width:100%;height:100%;background:#111;cursor:crosshair}
  #msg{position:absolute;left:10px;bottom:10px;background:rgba(0,0,0,.6);padding:6px 10px;border-radius:6px;color:#cfd3da;max-width:60vw}
  #hint{color:var(--muted);font-size:12px}
  .pill{font-size:11px;color:var(--muted);background:#15161a;border:1px solid var(--line);border-radius:10px;padding:2px 8px}
  #topbar{position:sticky;top:0;z-index:30;background:var(--panel)}
</style></head>
<body>
<div id="topbar">
<header>
  <div class="grp">
    <button id="open" class="pri">ファイルを開く…</button>
    <input id="file" type="file" accept="image/*" style="display:none">
    <input id="path" type="text" placeholder="またはパスを貼って Enter / 画像をD&D">
  </div>
  <div class="grp">
    <select id="method"><option value="cv">cv</option><option value="vision">vision</option><option value="hybrid">hybrid</option></select>
    <button id="auto">自動推定</button>
  </div>
  <div class="grp">
    <button id="addvp">消失点+（水平）</button>
    <button id="addvpv">消失点+（鉛直）</button>
    <button id="addray">パース線+</button>
    <button id="addchar">人物垂直線+</button>
    <button id="del" class="warn">選択を削除</button>
  </div>
  <div class="grp">
    <button id="addref">参考画像+</button>
    <input id="refimg" type="file" accept="image/*" style="display:none">
    <span id="hint3">透明度</span>
    <input id="ovop" type="range" min="10" max="100" value="70">
    <span id="oval" class="pill">70%</span>
  </div>
  <div class="grp">
    <label class="chk"><input id="snap" type="checkbox" checked>消失点を地平線へスナップ</label>
    <span id="hint">ガイド密度</span>
    <input id="density" type="range" min="0" max="40" value="14">
    <span id="dval" class="pill">14</span>
    <span id="hint2">線の太さ</span>
    <input id="lw" type="range" min="1" max="10" step="0.5" value="4">
    <span id="lval" class="pill">4</span>
  </div>
  <div class="grp">
    <button id="savepng" class="pri">PNG保存（場所を選ぶ）</button>
    <button id="savepngtr">透過PNG（線だけ）</button>
    <button id="savejson">JSON保存</button>
    <button id="reset" class="warn">リセット</button>
  </div>
</header>
<div class="legend" style="padding:6px 10px;background:var(--panel);border-bottom:1px solid var(--line)">
  <span><i style="background:var(--eye)"></i>アイレベル</span>
  <span><i style="background:var(--vp)"></i>消失点(水平)</span>
  <span><i style="background:var(--vpv)"></i>消失点(鉛直)</span>
  <span><i style="background:var(--guide)"></i>パースガイド</span>
  <span><i style="background:var(--vert)"></i>人物の鉛直線</span>
  <span><i style="background:var(--axis)"></i>人物の体軸(頭→足)</span>
  <span class="pill" id="info">未読込</span>
</div>
</div>
<div id="wrap"><canvas id="cv"></canvas><div id="msg">「ファイルを開く…」か画像をドラッグ&ドロップ。アイレベルを掴んで画像の外へカーソルを出すと傾けられます（消失点も連動）。空白ドラッグで上下移動。</div></div>

<script>
const C = {
  EYE:'#00c8ff', VP:'#ff28c8', VPV:'#ffb400', VERT:'#28dc46', AXIS:'#ffa000', GUIDE:'#ff78d2', SEL:'#ffffff'
};
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
const $ = id => document.getElementById(id);
let DPR = Math.max(1, window.devicePixelRatio||1);

const S = {
  path:'', name:'', img:null, iw:0, ih:0,
  view:{scale:1, ox:0, oy:0},
  horizon:{ya:0.5, yb:0.5},     // 正規化 y（x=0 と x=1 の高さ）
  vps:[],                        // {x,y,vertical,rays:[angle...]} angle=doc-px空間のラジアン
  chars:[],                      // {name, head:{x,y}, foot:{x,y}}
  overlays:[],                   // {img,name,corners:[{x,y}x4 TL,TR,BR,BL 正規化],opacity}
  density:14, snap:true, lw:4,
  sel:null, drag:null,
};
window.S = S;   // デバッグ/テスト用に公開
function letter(i){let s='',n=i+1;while(n>0){let r=(n-1)%26;s=String.fromCharCode(65+r)+s;n=Math.floor((n-1)/26);}return s;}
function horizonYat(nx){return S.horizon.ya + (S.horizon.yb - S.horizon.ya)*nx;}

// ---- 座標変換 ----
function fitView(){
  const w = cv.clientWidth, h = cv.clientHeight;
  if(!S.iw){S.view={scale:1,ox:0,oy:0};return;}
  const pad=20, sc=Math.min((w-pad*2)/S.iw,(h-pad*2)/S.ih);
  S.view.scale=sc; S.view.ox=(w-S.iw*sc)/2; S.view.oy=(h-S.ih*sc)/2;
}
function n2s(nx,ny){return [S.view.ox+nx*S.iw*S.view.scale, S.view.oy+ny*S.ih*S.view.scale];}
function s2n(sx,sy){return [(sx-S.view.ox)/(S.iw*S.view.scale),(sy-S.view.oy)/(S.ih*S.view.scale)];}
function imgRect(){return {x0:S.view.ox,y0:S.view.oy,x1:S.view.ox+S.iw*S.view.scale,y1:S.view.oy+S.ih*S.view.scale};}

// ---- セグメントを矩形でクリップ（Liang-Barsky）----
function clipSeg(x0,y0,x1,y1,r){
  let t0=0,t1=1; const dx=x1-x0,dy=y1-y0;
  const p=[-dx,dx,-dy,dy], q=[x0-r.x0,r.x1-x0,y0-r.y0,r.y1-y0];
  for(let i=0;i<4;i++){
    if(Math.abs(p[i])<1e-9){ if(q[i]<0) return null; }
    else{ const rr=q[i]/p[i];
      if(p[i]<0){ if(rr>t1)return null; if(rr>t0)t0=rr; }
      else{ if(rr<t0)return null; if(rr<t1)t1=rr; } }
  }
  return [x0+t0*dx,y0+t0*dy,x0+t1*dx,y0+t1*dy];
}

// ---- 描画 ----
function resize(){
  DPR=Math.max(1,window.devicePixelRatio||1);
  cv.width=cv.clientWidth*DPR; cv.height=cv.clientHeight*DPR;
  ctx.setTransform(DPR,0,0,DPR,0,0);
  if(S.iw) fitView();
  draw();
}
function drawFan(x,vx,vy,r,density){
  const inside = vx>=r.x0&&vx<=r.x1&&vy>=r.y0&&vy<=r.y1;
  let amin,amax;
  if(inside){amin=0;amax=Math.PI*2;}
  else{
    let angs=[[r.x0,r.y0],[r.x1,r.y0],[r.x1,r.y1],[r.x0,r.y1]].map(c=>Math.atan2(c[1]-vy,c[0]-vx));
    amin=Math.min(...angs);amax=Math.max(...angs);
    if(amax-amin>Math.PI){angs=angs.map(a=>a<0?a+2*Math.PI:a);amin=Math.min(...angs);amax=Math.max(...angs);}
  }
  const big=(r.x1-r.x0)+(r.y1-r.y0);
  x.beginPath();
  for(let k=0;k<=density;k++){
    const a=amin+(amax-amin)*k/Math.max(1,density);
    const seg=clipSeg(vx,vy,vx+Math.cos(a)*big*3,vy+Math.sin(a)*big*3,r);
    if(seg){x.moveTo(seg[0],seg[1]);x.lineTo(seg[2],seg[3]);}
  }
  x.stroke();
}
// ---- 参考画像の射影変形（単位正方形→四隅quadのホモグラフィ＋三角形メッシュ描画）----
function quadMap(p0,p1,p2,p3){  // p0..p3 = TL,TR,BR,BL（px）
  const dx1=p1[0]-p2[0], dx2=p3[0]-p2[0], dx3=p0[0]-p1[0]+p2[0]-p3[0];
  const dy1=p1[1]-p2[1], dy2=p3[1]-p2[1], dy3=p0[1]-p1[1]+p2[1]-p3[1];
  let g=0,h=0;
  const den=dx1*dy2-dy1*dx2;
  if(Math.abs(dx3)>1e-9||Math.abs(dy3)>1e-9){
    if(Math.abs(den)<1e-12) return null;
    g=(dx3*dy2-dy3*dx2)/den; h=(dx1*dy3-dy1*dx3)/den;
  }
  const a=p1[0]-p0[0]+g*p1[0], b=p3[0]-p0[0]+h*p3[0], c=p0[0];
  const d=p1[1]-p0[1]+g*p1[1], e=p3[1]-p0[1]+h*p3[1], f=p0[1];
  return (u,v)=>{const w=g*u+h*v+1; return [(a*u+b*v+c)/w,(d*u+e*v+f)/w];};
}
function drawImageTri(x,img,s0,s1,s2,d0,d1,d2){
  const den=s0[0]*(s1[1]-s2[1])+s1[0]*(s2[1]-s0[1])+s2[0]*(s0[1]-s1[1]);
  if(Math.abs(den)<1e-9) return;
  const m11=(d0[0]*(s1[1]-s2[1])+d1[0]*(s2[1]-s0[1])+d2[0]*(s0[1]-s1[1]))/den;
  const m12=(d0[1]*(s1[1]-s2[1])+d1[1]*(s2[1]-s0[1])+d2[1]*(s0[1]-s1[1]))/den;
  const m21=(d0[0]*(s2[0]-s1[0])+d1[0]*(s0[0]-s2[0])+d2[0]*(s1[0]-s0[0]))/den;
  const m22=(d0[1]*(s2[0]-s1[0])+d1[1]*(s0[0]-s2[0])+d2[1]*(s1[0]-s0[0]))/den;
  const dx=(d0[0]*(s1[0]*s2[1]-s2[0]*s1[1])+d1[0]*(s2[0]*s0[1]-s0[0]*s2[1])+d2[0]*(s0[0]*s1[1]-s1[0]*s0[1]))/den;
  const dy=(d0[1]*(s1[0]*s2[1]-s2[0]*s1[1])+d1[1]*(s2[0]*s0[1]-s0[0]*s2[1])+d2[1]*(s0[0]*s1[1]-s1[0]*s0[1]))/den;
  // クリップは重心に向けて僅かに拡張（三角形間の継ぎ目消し）
  const cx=(d0[0]+d1[0]+d2[0])/3, cy=(d0[1]+d1[1]+d2[1])/3, EX=1.02;
  const q=p=>[cx+(p[0]-cx)*EX, cy+(p[1]-cy)*EX];
  const e0=q(d0),e1=q(d1),e2=q(d2);
  x.save();
  x.beginPath();x.moveTo(e0[0],e0[1]);x.lineTo(e1[0],e1[1]);x.lineTo(e2[0],e2[1]);x.closePath();x.clip();
  x.transform(m11,m12,m21,m22,dx,dy);
  x.drawImage(img,0,0);
  x.restore();
}
// overlay を P(正規化→px) で描く。N×N メッシュで射影近似。
function drawOverlayOn(x,ov,P,selected,handleR){
  const map=quadMap(P(ov.corners[0].x,ov.corners[0].y),P(ov.corners[1].x,ov.corners[1].y),
                    P(ov.corners[2].x,ov.corners[2].y),P(ov.corners[3].x,ov.corners[3].y));
  if(!map||!ov.img) return;
  const iw=ov.img.naturalWidth||ov.img.width, ih=ov.img.naturalHeight||ov.img.height;
  const N=8;
  x.save();x.globalAlpha=ov.opacity;
  for(let j=0;j<N;j++)for(let i=0;i<N;i++){
    const u0=i/N,u1=(i+1)/N,v0=j/N,v1=(j+1)/N;
    const s00=[u0*iw,v0*ih],s10=[u1*iw,v0*ih],s11=[u1*iw,v1*ih],s01=[u0*iw,v1*ih];
    const d00=map(u0,v0),d10=map(u1,v0),d11=map(u1,v1),d01=map(u0,v1);
    drawImageTri(x,ov.img,s00,s10,s11,d00,d10,d11);
    drawImageTri(x,ov.img,s00,s11,s01,d00,d11,d01);
  }
  x.restore();
  if(selected){
    const pts=ov.corners.map(c=>P(c.x,c.y));
    x.strokeStyle=C.SEL;x.lineWidth=1.5;x.setLineDash([6,4]);
    x.beginPath();x.moveTo(pts[0][0],pts[0][1]);for(let k=1;k<4;k++)x.lineTo(pts[k][0],pts[k][1]);x.closePath();x.stroke();x.setLineDash([]);
    pts.forEach(p=>{x.fillStyle='#2563eb';x.beginPath();x.arc(p[0],p[1],handleR||6,0,Math.PI*2);x.fill();
      x.strokeStyle='#fff';x.lineWidth=1.5;x.beginPath();x.arc(p[0],p[1],handleR||6,0,Math.PI*2);x.stroke();});
  }
}
// VP から角度 ang（doc-px空間）のパース線分（画面px）を返す
function raySeg(v,ri,P,r){
  const vp=P(v.x,v.y);
  const dir=[Math.cos(v.rays[ri]),Math.sin(v.rays[ri])];
  const big=(r.x1-r.x0)+(r.y1-r.y0);
  return clipSeg(vp[0],vp[1],vp[0]+dir[0]*big*3,vp[1]+dir[1]*big*3,r);
}
function cross(x,y,col,rad,w){
  ctx.strokeStyle=col;ctx.lineWidth=w||2;
  ctx.beginPath();ctx.moveTo(x-rad,y);ctx.lineTo(x+rad,y);ctx.moveTo(x,y-rad);ctx.lineTo(x,y+rad);ctx.stroke();
  ctx.beginPath();ctx.arc(x,y,rad,0,Math.PI*2);ctx.stroke();
}
function dot(x,y,col,rad){ctx.fillStyle=col;ctx.beginPath();ctx.arc(x,y,rad,0,Math.PI*2);ctx.fill();}
function label(x,y,t,col){const fs=Math.round(12+S.lw*1.6);ctx.font=fs+'px system-ui';ctx.lineWidth=Math.max(3,S.lw);ctx.strokeStyle='rgba(0,0,0,.85)';ctx.strokeText(t,x,y);ctx.fillStyle=col;ctx.fillText(t,x,y);}

function draw(){
  ctx.clearRect(0,0,cv.clientWidth,cv.clientHeight);
  if(!S.img){return;}
  const r=imgRect();
  ctx.drawImage(S.img,r.x0,r.y0,r.x1-r.x0,r.y1-r.y0);
  const LW=S.lw, GW=Math.max(1,S.lw*0.5), CR=6+S.lw*1.4, DR=3+S.lw*0.9;
  // 参考画像（アタリ・ラフ）: 背景の上・線の下
  S.overlays.forEach((ov,i)=>drawOverlayOn(ctx,ov,(nx,ny)=>n2s(nx,ny),
    S.sel&&S.sel.type==='ov'&&S.sel.i===i, 7));
  // パースガイド（やや濃いめ。密度0=扇を描かない→レイだけ残せる）
  if(S.density>0){
    ctx.save();ctx.globalAlpha=0.6;
    S.vps.forEach(v=>{const [sx,sy]=n2s(v.x,v.y);ctx.strokeStyle=C.GUIDE;ctx.lineWidth=GW;drawFan(ctx,sx,sy,r,S.density);});
    ctx.restore();
  }
  // 個別パース線（レイ）: 濃く・選択可能
  S.vps.forEach((v,vi)=>{ (v.rays||[]).forEach((_,ri)=>{
    const seg=raySeg(v,ri,(nx,ny)=>n2s(nx,ny),r);
    if(!seg) return;
    const selr=S.sel&&S.sel.type==='ray'&&S.sel.vi===vi&&S.sel.ri===ri;
    ctx.strokeStyle=selr?C.SEL:C.GUIDE;ctx.lineWidth=selr?LW+1:Math.max(1.5,LW*0.8);
    ctx.beginPath();ctx.moveTo(seg[0],seg[1]);ctx.lineTo(seg[2],seg[3]);ctx.stroke();
  });});
  // 傾け中: 半透明の水平基準線（アイレベル中央の高さに）
  if(S.drag&&S.drag.type==='horizon'&&S.drag.rotating){
    const my=(S.drag.pivotN?S.drag.pivotN.y:(S.horizon.ya+S.horizon.yb)/2);
    const sy=n2s(0,my)[1];
    ctx.save();ctx.globalAlpha=0.45;ctx.strokeStyle='#ffffff';ctx.lineWidth=Math.max(1,LW*0.6);
    ctx.setLineDash([12,8]);ctx.beginPath();ctx.moveTo(r.x0,sy);ctx.lineTo(r.x1,sy);ctx.stroke();
    ctx.setLineDash([]);ctx.restore();
    label(r.x0+6,sy-6,'水平(0°)',  '#ffffff');
  }
  // アイレベル
  const [ax,ay]=n2s(0,S.horizon.ya), [bx,by]=n2s(1,S.horizon.yb);
  const seg=clipSeg(ax,ay,bx,by,r);
  if(seg){ctx.strokeStyle=C.EYE;ctx.lineWidth=LW;ctx.beginPath();ctx.moveTo(seg[0],seg[1]);ctx.lineTo(seg[2],seg[3]);ctx.stroke();
    label(seg[0]+6,seg[1]-6,'EYE LEVEL / アイレベル',C.EYE);}
  // 消失点
  S.vps.forEach((v,i)=>{const [sx,sy]=n2s(v.x,v.y);const col=v.vertical?C.VPV:C.VP;
    cross(sx,sy,col,CR,LW);label(sx+CR+4,sy-CR,(v.vertical?'VVP':'VP')+(i+1),col);
    if(S.sel&&S.sel.type==='vp'&&S.sel.i===i){ctx.strokeStyle=C.SEL;ctx.lineWidth=Math.max(1,LW*0.5);ctx.beginPath();ctx.arc(sx,sy,CR+5,0,Math.PI*2);ctx.stroke();}});
  // 人物の垂直線
  S.chars.forEach((c,i)=>{
    const [hx,hy]=n2s(c.head.x,c.head.y), [fx,fy]=n2s(c.foot.x,c.foot.y);
    ctx.strokeStyle=C.VERT;ctx.lineWidth=LW;ctx.beginPath();
    ctx.moveTo(fx,Math.min(hy,fy)-Math.abs(fy-hy)*0.12-6);ctx.lineTo(fx,Math.max(hy,fy)+6);ctx.stroke();
    ctx.strokeStyle=C.AXIS;ctx.lineWidth=Math.max(1.5,LW*0.8);ctx.setLineDash([10,7]);ctx.beginPath();ctx.moveTo(hx,hy);ctx.lineTo(fx,fy);ctx.stroke();ctx.setLineDash([]);
    dot(hx,hy,C.AXIS,DR);dot(fx,fy,C.VERT,DR);
    label(fx+DR+3,hy-8,c.name||('人物'+letter(i)),C.VERT);
    if(S.sel&&S.sel.type==='char'&&S.sel.i===i){ctx.strokeStyle=C.SEL;ctx.lineWidth=Math.max(1,LW*0.5);
      ctx.strokeRect(Math.min(hx,fx)-8,Math.min(hy,fy)-8,Math.abs(fx-hx)+16,Math.abs(fy-hy)+16);}
  });
}

// ---- ヒットテスト ----
function near(sx,sy,px,py,th){return Math.hypot(sx-px,sy-py)<=th;}
function pointInQuad(mx,my,pts){
  let inside=false;
  for(let i=0,j=3;i<4;j=i++){
    const xi=pts[i][0],yi=pts[i][1],xj=pts[j][0],yj=pts[j][1];
    if(((yi>my)!==(yj>my)) && (mx < (xj-xi)*(my-yi)/(yj-yi)+xi)) inside=!inside;
  }
  return inside;
}
function hit(mx,my){
  const th=10;
  for(let i=0;i<S.chars.length;i++){const c=S.chars[i];
    let p=n2s(c.head.x,c.head.y); if(near(mx,my,p[0],p[1],th))return{type:'char',i,sub:'head'};
    p=n2s(c.foot.x,c.foot.y); if(near(mx,my,p[0],p[1],th))return{type:'char',i,sub:'foot'};}
  for(let i=0;i<S.vps.length;i++){const p=n2s(S.vps[i].x,S.vps[i].y); if(near(mx,my,p[0],p[1],12))return{type:'vp',i};}
  // 個別パース線（レイ）
  const r=imgRect();
  for(let vi=0;vi<S.vps.length;vi++){const v=S.vps[vi];
    for(let ri=0;ri<(v.rays||[]).length;ri++){
      const seg=raySeg(v,ri,(nx,ny)=>n2s(nx,ny),r);
      if(seg && distToSeg(mx,my,seg[0],seg[1],seg[2],seg[3])<7)return{type:'ray',vi,ri};
    }}
  // 参考画像: 角ハンドル → 本体（後に追加したものを優先）
  for(let i=S.overlays.length-1;i>=0;i--){const ov=S.overlays[i];
    const pts=ov.corners.map(c=>n2s(c.x,c.y));
    for(let ci=0;ci<4;ci++){ if(near(mx,my,pts[ci][0],pts[ci][1],11))return{type:'ov',i,sub:ci}; }
    if(pointInQuad(mx,my,pts))return{type:'ov',i,sub:'body'};
  }
  // アイレベル端 / 本体
  const a=n2s(0,S.horizon.ya), b=n2s(1,S.horizon.yb);
  if(near(mx,my,a[0],a[1],th))return{type:'horizon',sub:'a'};
  if(near(mx,my,b[0],b[1],th))return{type:'horizon',sub:'b'};
  // 線分への距離
  const dl=distToSeg(mx,my,a[0],a[1],b[0],b[1]);
  if(dl<8)return{type:'horizon',sub:'body'};
  return null;
}
function distToSeg(px,py,x0,y0,x1,y1){const dx=x1-x0,dy=y1-y0,l2=dx*dx+dy*dy;
  let t=l2?((px-x0)*dx+(py-y0)*dy)/l2:0; t=Math.max(0,Math.min(1,t));
  return Math.hypot(px-(x0+t*dx),py-(y0+t*dy));}

function clampN(v){return Math.max(-2,Math.min(3,v));}     // アイレベルy等
function clampW(v){return Math.max(-12,Math.min(12,v));}    // 消失点は画角外も許容
function applySnap(){ if(S.snap){S.vps.forEach(v=>{if(!v.vertical)v.y=horizonYat(v.x);});} }

// 点 (sx,sy) をピボット Ps まわりに回転（screen座標）
function rotPt(sx,sy,Ps,c,s){const dx=sx-Ps[0],dy=sy-Ps[1];return [Ps[0]+dx*c-dy*s, Ps[1]+dx*s+dy*c];}
// アイレベルを delta だけ回転し、消失点も一緒に回す（screen Ps まわり）
function rotateHorizon(delta,Ps){
  const c=Math.cos(delta),s=Math.sin(delta);
  let A=n2s(0,S.horizon.ya), B=n2s(1,S.horizon.yb);
  A=rotPt(A[0],A[1],Ps,c,s); B=rotPt(B[0],B[1],Ps,c,s);
  const r=imgRect();
  const dx=B[0]-A[0], m=Math.abs(dx)<1e-6?0:(B[1]-A[1])/dx;
  const yl=A[1]+m*(r.x0-A[0]), yr=A[1]+m*(r.x1-A[0]);
  const nyl=s2n(r.x0,yl)[1], nyr=s2n(r.x1,yr)[1];
  if(Math.abs(nyr-nyl)>1.5) return;   // 急すぎ(ほぼ垂直)は無視
  // 誤差1°未満は水平へ自動補正（screen角度で判定）
  const degNow=Math.abs(Math.atan2(yr-yl,r.x1-r.x0)*180/Math.PI);
  if(degNow<1.0){const mid=(nyl+nyr)/2;S.horizon.ya=clampN(mid);S.horizon.yb=clampN(mid);}
  else{S.horizon.ya=clampN(nyl); S.horizon.yb=clampN(nyr);}
  S.vps.forEach(v=>{const sp=n2s(v.x,v.y);const rp=rotPt(sp[0],sp[1],Ps,c,s);const np=s2n(rp[0],rp[1]);v.x=clampW(np[0]);v.y=clampW(np[1]);});
}

// ---- マウス ----
let dragStart=null;
cv.addEventListener('mousedown',e=>{
  if(!S.img)return; const m=mouse(e);
  const h=hit(m.x,m.y);
  if(h&&(h.type==='vp'||h.type==='char'||h.type==='ov')) S.sel={type:h.type,i:h.i};
  else if(h&&h.type==='ray') S.sel={type:'ray',vi:h.vi,ri:h.ri};
  S.drag = h || {type:'horizon',sub:'body'};
  if(!h) S.sel=null;
  if(S.sel&&S.sel.type==='ov'){const op=S.overlays[S.sel.i].opacity;$('ovop').value=Math.round(op*100);$('oval').textContent=Math.round(op*100)+'%';}
  S.drag.lastY=m.y; S.drag.lastX=m.x; S.drag.rotating=false;
  dragStart={m, horizon:{...S.horizon}};
  draw();
});
window.addEventListener('mousemove',e=>{
  if(!S.drag||!S.img)return; const m=mouse(e); const [nx,ny]=s2n(m.x,m.y);
  const d=S.drag;
  if(d.type==='vp'){const v=S.vps[d.i]; v.x=clampW(nx); v.y=(S.snap&&!v.vertical)?horizonYat(v.x):clampW(ny);}
  else if(d.type==='char'){const c=S.chars[d.i]; c[d.sub].x=clampN(nx); c[d.sub].y=clampN(ny);}
  else if(d.type==='ray'){
    // レイの回転: VP→マウスの角度（doc-px空間）に合わせる
    const v=S.vps[d.vi];
    v.rays[d.ri]=Math.atan2((ny-v.y)*S.ih,(nx-v.x)*S.iw);
  }
  else if(d.type==='ov'){
    const ov=S.overlays[d.i];
    if(d.sub==='body'){
      const dx=(m.x-d.lastX)/(S.iw*S.view.scale), dy=(m.y-d.lastY)/(S.ih*S.view.scale);
      ov.corners.forEach(c=>{c.x=clampN(c.x+dx);c.y=clampN(c.y+dy);});
      d.lastX=m.x; d.lastY=m.y;
    }else{
      ov.corners[d.sub]={x:clampN(nx),y:clampN(ny)};
    }
  }
  else if(d.type==='horizon'){
    if(d.sub==='a'){S.horizon.ya=clampN(ny);applySnap();}
    else if(d.sub==='b'){S.horizon.yb=clampN(ny);applySnap();}
    else{
      const r=imgRect();
      const inside = m.x>=r.x0&&m.x<=r.x1&&m.y>=r.y0&&m.y<=r.y1;
      if(inside){
        // 画像内 → 平行移動（傾き保持・消失点も一緒に上下）
        const dy=(m.y-d.lastY)/(S.ih*S.view.scale);
        S.horizon.ya=clampN(S.horizon.ya+dy); S.horizon.yb=clampN(S.horizon.yb+dy);
        S.vps.forEach(v=>v.y=clampW(v.y+dy));
        d.rotating=false; applySnap();
      } else {
        // 画像の外 → 傾ける（回転）。ピボット=アイレベル中央。消失点も連動回転。
        if(!d.rotating){d.rotating=true; d.pivotN={x:0.5,y:(S.horizon.ya+S.horizon.yb)/2}; d.prevAng=null;}
        const Ps=n2s(d.pivotN.x,d.pivotN.y);
        const ang=Math.atan2(m.y-Ps[1],m.x-Ps[0]);
        if(d.prevAng===null){d.prevAng=ang;}
        const delta=ang-d.prevAng; d.prevAng=ang;
        if(delta) rotateHorizon(delta,Ps);
        applySnap();
      }
    }
    d.lastY=m.y; d.lastX=m.x;
  }
  draw();
});
window.addEventListener('mouseup',()=>{S.drag=null;dragStart=null;});
function mouse(e){const r=cv.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top};}
window.addEventListener('keydown',e=>{if((e.key==='Delete'||e.key==='Backspace')&&S.sel)delSel();});

// ---- 操作 ----
function setMsg(t){$('msg').textContent=t;}
function openInfo(j){
  const img=new Image();
  img.onload=()=>{S.img=img;S.iw=j.width;S.ih=j.height;S.path=j.path;S.name=j.name;
    S.horizon={ya:0.5,yb:0.5};S.vps=[];S.chars=[];S.overlays=[];S.sel=null;
    $('path').value=j.path;
    $('info').textContent=`${j.name}  ${j.width}×${j.height}`;
    fitView();draw();setMsg('読込完了。アイレベル/消失点を配置、または「自動推定」。画面外ドラッグで傾け可。');};
  img.onerror=()=>setMsg('画像の表示に失敗');
  img.src='/image?path='+encodeURIComponent(j.path);
}
async function openTyped(){
  const path=$('path').value.trim(); if(!path){setMsg('「ファイルを開く…」で選択するか、パスを貼ってEnter');return;}
  setMsg('読込中…');
  const r=await fetch('/api/open?path='+encodeURIComponent(path));
  const j=await r.json(); if(!r.ok){setMsg('エラー: '+(j.error||r.status));return;}
  openInfo(j);
}
async function uploadFile(file){
  setMsg('読込中… '+file.name);
  const fd=new FormData(); fd.append('file',file);
  const r=await fetch('/api/upload',{method:'POST',body:fd});
  const j=await r.json(); if(!r.ok){setMsg('アップロード失敗: '+(j.error||r.status));return;}
  openInfo(j);
}
async function auto(){
  if(!S.path){setMsg('先に画像を開いてください');return;}
  const method=$('method').value; setMsg(method+' で推定中…（visionは数秒〜）');
  const r=await fetch('/api/detect',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({path:S.path,method})});
  const j=await r.json(); if(!r.ok){setMsg('推定エラー: '+(j.error||r.status));return;}
  loadResult(j); setMsg(method+' 推定を反映: '+(j.notes||''));
}
function loadResult(j){
  if(j.eye_level&&j.eye_level.a&&j.eye_level.b){
    const a=j.eye_level.a,b=j.eye_level.b; // 直線から x=0,1 の y を求める
    const dx=b[0]-a[0];
    if(Math.abs(dx)>1e-6){const s=(b[1]-a[1])/dx; S.horizon.ya=a[1]-s*a[0]; S.horizon.yb=a[1]+s*(1-a[0]);}
    else{S.horizon.ya=a[1];S.horizon.yb=b[1];}
  }
  S.vps=(j.vanishing_points||[]).map(v=>({x:v.x,y:v.y,vertical:(v.axis==='vertical'),rays:(v.rays||[]).slice()}));
  S.chars=(j.characters||[]).map((c,i)=>({name:c.name||('人物'+letter(i)),head:{x:c.head[0],y:c.head[1]},foot:{x:c.foot[0],y:c.foot[1]}}));
  applySnap();draw();
}
function annotation(){
  return {method:'edit', image:{path:S.path,width:S.iw,height:S.ih},
    eye_level:{a:[0,S.horizon.ya],b:[1,S.horizon.yb]},
    vanishing_points:S.vps.map((v,i)=>({x:v.x,y:v.y,label:(v.vertical?'VVP':'VP')+(i+1),axis:v.vertical?'vertical':'horizontal',rays:(v.rays||[]).slice()})),
    characters:S.chars.map((c,i)=>({name:c.name||('人物'+letter(i)),head:[c.head.x,c.head.y],foot:[c.foot.x,c.foot.y]})),
    overlays:S.overlays.map(o=>({name:o.name,opacity:o.opacity,corners:o.corners.map(c=>[c.x,c.y])})),
    guide_density:S.density, line_scale:S.lw/4, notes:'editor'};
}
function baseName(){return S.name?S.name.replace(/\.[^.]+$/,''):'perspective';}
function download(blob,name){const u=URL.createObjectURL(blob);const a=document.createElement('a');
  a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),2000);}

// 焼き込みPNGを「ブラウザ側でフル解像度生成」する（サーバ非依存＝固まらない・確実に中身入り）。
// 画面表示と同じ見た目を、原寸キャンバスに描く。線幅は表示→原寸の倍率(1/scale)で換算。
function renderFullCanvas(withImage){
  const W=S.iw,H=S.ih;
  const c=document.createElement('canvas'); c.width=W; c.height=H;
  const x=c.getContext('2d');
  if(withImage!==false) x.drawImage(S.img,0,0,W,H);   // false=透過(線だけ)
  const sc=1/Math.max(S.view.scale,1e-6);
  const LW=Math.max(2,S.lw*sc), GW=Math.max(1,LW*0.5), CR=(6+S.lw*1.4)*sc, DR=(3+S.lw*0.9)*sc;
  const FS=Math.max(11,Math.round((12+S.lw*1.6)*sc));
  const P=(nx,ny)=>[nx*W,ny*H];
  const r={x0:0,y0:0,x1:W,y1:H};
  const lbl=(px,py,t,col)=>{x.font=FS+'px system-ui';x.lineWidth=Math.max(3,LW);x.strokeStyle='rgba(0,0,0,.85)';x.strokeText(t,px,py);x.fillStyle=col;x.fillText(t,px,py);};
  // 参考画像（アタリ）: PNG保存(withImage)にのみ焼き込む。透過(線だけ)には入れない
  if(withImage!==false) S.overlays.forEach(ov=>drawOverlayOn(x,ov,(nx,ny)=>P(nx,ny),false,0));
  // ガイド（密度0=扇なし）
  if(S.density>0){
    x.save();x.globalAlpha=0.6;x.strokeStyle=C.GUIDE;x.lineWidth=GW;
    S.vps.forEach(v=>{const [vx,vy]=P(v.x,v.y);drawFan(x,vx,vy,r,S.density);});
    x.restore();
  }
  // 個別パース線（レイ）
  S.vps.forEach(v=>{(v.rays||[]).forEach((_,ri)=>{
    const seg=raySeg(v,ri,(nx,ny)=>P(nx,ny),r);
    if(seg){x.strokeStyle=C.GUIDE;x.lineWidth=Math.max(1.5,LW*0.8);
      x.beginPath();x.moveTo(seg[0],seg[1]);x.lineTo(seg[2],seg[3]);x.stroke();}
  });});
  // アイレベル
  const [ax,ay]=P(0,S.horizon.ya),[bx,by]=P(1,S.horizon.yb);
  const seg=clipSeg(ax,ay,bx,by,r);
  if(seg){x.strokeStyle=C.EYE;x.lineWidth=LW;x.beginPath();x.moveTo(seg[0],seg[1]);x.lineTo(seg[2],seg[3]);x.stroke();lbl(seg[0]+6*sc,seg[1]-6*sc,'EYE LEVEL / アイレベル',C.EYE);}
  // 消失点
  S.vps.forEach((v,i)=>{const [vx,vy]=P(v.x,v.y);const col=v.vertical?C.VPV:C.VP;
    x.strokeStyle=col;x.lineWidth=LW;
    x.beginPath();x.moveTo(vx-CR,vy);x.lineTo(vx+CR,vy);x.moveTo(vx,vy-CR);x.lineTo(vx,vy+CR);x.stroke();
    x.beginPath();x.arc(vx,vy,CR,0,Math.PI*2);x.stroke();
    lbl(vx+CR+4*sc,vy-CR,(v.vertical?'VVP':'VP')+(i+1),col);});
  // 人物の垂直線
  S.chars.forEach((c2,i)=>{const [hx,hy]=P(c2.head.x,c2.head.y),[fx,fy]=P(c2.foot.x,c2.foot.y);
    x.strokeStyle=C.VERT;x.lineWidth=LW;x.beginPath();
    x.moveTo(fx,Math.min(hy,fy)-Math.abs(fy-hy)*0.12-6*sc);x.lineTo(fx,Math.max(hy,fy)+6*sc);x.stroke();
    x.strokeStyle=C.AXIS;x.lineWidth=Math.max(1.5,LW*0.8);x.setLineDash([10*sc,7*sc]);x.beginPath();x.moveTo(hx,hy);x.lineTo(fx,fy);x.stroke();x.setLineDash([]);
    x.fillStyle=C.AXIS;x.beginPath();x.arc(hx,hy,DR,0,Math.PI*2);x.fill();
    x.fillStyle=C.VERT;x.beginPath();x.arc(fx,fy,DR,0,Math.PI*2);x.fill();
    lbl(fx+DR+3*sc,hy-8*sc,c2.name||('人物'+letter(i)),C.VERT);});
  return c;
}
// dataURL を同期で Blob 化（await を挟まずに作るので showSaveFilePicker のユーザ操作が切れない）
function dataURLtoBlob(url){const i=url.indexOf(',');const bin=atob(url.slice(i+1));
  const arr=new Uint8Array(bin.length);for(let k=0;k<bin.length;k++)arr[k]=bin.charCodeAt(k);
  return new Blob([arr],{type:'image/png'});}

// blob は呼ぶ前に作っておく（空ファイル防止）。ピッカーはクリック操作中に開く。
async function saveBlobPicker(blob,name,types,label){
  if(window.showSaveFilePicker){
    let handle;
    try{ handle=await window.showSaveFilePicker({suggestedName:name,types}); }
    catch(e){ if(e&&e.name==='AbortError'){setMsg('保存をキャンセルしました');return;} handle=null; }
    if(handle){
      try{ const w=await handle.createWritable(); await w.write(blob); await w.close(); }
      catch(e){ setMsg(label+'書込失敗: '+(e.message||e)); return; }
      setMsg(label+'を保存しました ('+Math.max(1,Math.round(blob.size/1024))+'KB)。'); return;
    }
  }
  download(blob,name);
  setMsg(label+'をダウンロードしました（保存先の指定はChrome/Edgeで可能）。');
}
async function savePNG(){
  if(!S.path){setMsg('先に画像を開いてください');return;}
  let blob;
  try{ blob=dataURLtoBlob(renderFullCanvas(true).toDataURL('image/png')); }
  catch(e){ setMsg('PNG生成失敗: '+(e.message||e)); return; }
  await saveBlobPicker(blob, baseName()+'.perspective.png',
    [{description:'PNG画像',accept:{'image/png':['.png']}}], 'PNG');
}
// 線だけ（アイレベル・パースガイド・人物垂直線）を透過背景で保存
async function savePNGLines(){
  if(!S.path){setMsg('先に画像を開いてください');return;}
  let blob;
  try{ blob=dataURLtoBlob(renderFullCanvas(false).toDataURL('image/png')); }
  catch(e){ setMsg('透過PNG生成失敗: '+(e.message||e)); return; }
  await saveBlobPicker(blob, baseName()+'.perspective_lines.png',
    [{description:'PNG画像(透過)',accept:{'image/png':['.png']}}], '透過PNG');
}
async function saveJSON(){
  if(!S.path){setMsg('先に画像を開いてください');return;}
  const blob=new Blob([JSON.stringify(annotation(),null,2)],{type:'application/json'});
  await saveBlobPicker(blob, baseName()+'.perspective.json',
    [{description:'JSON',accept:{'application/json':['.json']}}], 'JSON');
}
function addVP(vertical){const x=0.5,y=vertical?0.12:horizonYat(0.5);S.vps.push({x,y,vertical,rays:[]});S.sel={type:'vp',i:S.vps.length-1};draw();}
function addChar(){const i=S.chars.length;S.chars.push({name:'人物'+letter(i),head:{x:0.45,y:0.35},foot:{x:0.45,y:0.85}});S.sel={type:'char',i};draw();}
// 個別パース線: 選択中のVP（無ければ最後のVP）に1本足す。ドラッグで角度を合わせる。
function addRay(){
  if(!S.vps.length){setMsg('先に消失点を追加してください');return;}
  const vi=(S.sel&&S.sel.type==='vp')?S.sel.i:S.vps.length-1;
  const v=S.vps[vi]; v.rays=v.rays||[];
  // 既定角: 上向き45°から少しずつずらす（重なり防止。アイレベルが低くても掴みやすい）
  v.rays.push(-Math.PI/4 - v.rays.length*0.22);
  S.sel={type:'ray',vi,ri:v.rays.length-1};
  draw();setMsg('パース線を追加（VP'+(vi+1)+'）。線をドラッグで角度調整、Delで削除。');
}
// 参考画像（アタリ・ラフ用）: 中央に40%幅で置き、四隅をパースに合わせてドラッグ
function addOverlayFile(file){
  const rd=new FileReader();
  rd.onload=()=>{const img=new Image();
    img.onload=()=>{
      const w=0.4, h=0.4*(img.naturalHeight/img.naturalWidth)*(S.iw/S.ih);
      const cx=0.5, cy=0.5;
      S.overlays.push({img, name:file.name, opacity:0.7,
        corners:[{x:cx-w/2,y:cy-h/2},{x:cx+w/2,y:cy-h/2},{x:cx+w/2,y:cy+h/2},{x:cx-w/2,y:cy+h/2}]});
      S.sel={type:'ov',i:S.overlays.length-1};
      draw();setMsg('参考画像を追加: '+file.name+'。四隅ハンドルをパース線に沿わせると射影変形されます。');
    };
    img.onerror=()=>setMsg('参考画像の読込に失敗: '+file.name);
    img.src=rd.result;
  };
  rd.readAsDataURL(file);
}
function delSel(){if(!S.sel)return;
  if(S.sel.type==='vp')S.vps.splice(S.sel.i,1);
  if(S.sel.type==='char')S.chars.splice(S.sel.i,1);
  if(S.sel.type==='ray'){const v=S.vps[S.sel.vi]; if(v&&v.rays)v.rays.splice(S.sel.ri,1);}
  if(S.sel.type==='ov')S.overlays.splice(S.sel.i,1);
  S.sel=null;draw();}
function reset(){S.horizon={ya:0.5,yb:0.5};S.vps=[];S.chars=[];S.overlays=[];S.sel=null;draw();setMsg('リセットしました');}

$('open').onclick=()=>$('file').click();
$('file').onchange=e=>{const f=e.target.files&&e.target.files[0]; if(f)uploadFile(f); e.target.value='';};
$('path').addEventListener('keydown',e=>{if(e.key==='Enter')openTyped();});
$('auto').onclick=auto;
// ドラッグ&ドロップで開く
const wrap=document.getElementById('wrap');
['dragenter','dragover'].forEach(ev=>wrap.addEventListener(ev,e=>{e.preventDefault();e.stopPropagation();if(e.dataTransfer)e.dataTransfer.dropEffect='copy';wrap.style.outline='3px dashed #2563eb';wrap.style.outlineOffset='-6px';}));
['dragleave'].forEach(ev=>wrap.addEventListener(ev,e=>{e.preventDefault();wrap.style.outline='';}));
wrap.addEventListener('drop',e=>{e.preventDefault();e.stopPropagation();wrap.style.outline='';
  const f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];
  if(f){ if(f.type&&f.type.indexOf('image')!==0){setMsg('画像ファイルをドロップしてください: '+f.name);return;} uploadFile(f);} });
// ブラウザがファイルを開いて遷移するのを全体で抑止
window.addEventListener('dragover',e=>e.preventDefault());
window.addEventListener('drop',e=>e.preventDefault());
$('addvp').onclick=()=>addVP(false);
$('addvpv').onclick=()=>addVP(true);
$('addray').onclick=addRay;
$('addchar').onclick=addChar;
$('addref').onclick=()=>{if(!S.img){setMsg('先に背景画像を開いてください');return;}$('refimg').click();};
$('refimg').onchange=e=>{const f=e.target.files&&e.target.files[0]; if(f)addOverlayFile(f); e.target.value='';};
$('ovop').oninput=e=>{const v=+e.target.value;$('oval').textContent=v+'%';
  if(S.sel&&S.sel.type==='ov'){S.overlays[S.sel.i].opacity=v/100;draw();}
  else if(S.overlays.length){S.overlays[S.overlays.length-1].opacity=v/100;draw();}};
$('del').onclick=delSel;
$('savepng').onclick=savePNG;
$('savepngtr').onclick=savePNGLines;
$('savejson').onclick=saveJSON;
$('reset').onclick=reset;
$('snap').onchange=e=>{S.snap=e.target.checked;applySnap();draw();};
$('density').oninput=e=>{S.density=+e.target.value;$('dval').textContent=e.target.value;draw();};
$('lw').oninput=e=>{S.lw=+e.target.value;$('lval').textContent=e.target.value;draw();};
window.addEventListener('resize',resize);
resize();
fetch('/api/config').then(r=>r.json()).then(j=>{if(j.image){$('path').value=j.image;openTyped();}});
</script>
</body></html>
"""


if __name__ == "__main__":
    raise SystemExit(main())

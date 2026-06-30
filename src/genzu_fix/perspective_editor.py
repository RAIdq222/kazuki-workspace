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
            with Image.open(path) as im:
                w, h = im.size
        except Exception as e:
            return jsonify({"error": f"画像を開けません: {e}"}), 400
        return jsonify({"ok": True, "path": os.path.abspath(path),
                        "name": os.path.basename(path), "width": w, "height": h})

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

    @app.post("/api/save")
    def api_save():
        b = request.json or {}
        path = (b.get("path") or "").strip().strip('"')
        ann = b.get("annotation") or {}
        if not _ok(path):
            return jsonify({"error": "画像が見つかりません"}), 404
        stem = os.path.splitext(os.path.basename(path))[0]
        out_dir = b.get("out_dir") or os.path.join("work", "_perspective", stem)
        os.makedirs(out_dir, exist_ok=True)
        json_path = os.path.join(out_dir, f"{stem}.edit.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(ann, f, ensure_ascii=False, indent=2)
        try:
            res = perspective.PerspectiveResult.from_json(ann)
            png_path = os.path.join(out_dir, f"{stem}.edit.png")
            perspective.render(res, path, png_path, title="EDIT")
        except Exception as e:
            return jsonify({"ok": True, "json": os.path.abspath(json_path),
                            "png_error": str(e)})
        return jsonify({"ok": True, "json": os.path.abspath(json_path),
                        "png": os.path.abspath(png_path)})

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
</style></head>
<body>
<header>
  <div class="grp">
    <input id="path" type="text" placeholder="画像ファイルのパス（例 C:\...\cut.png）">
    <button id="open" class="pri">開く</button>
  </div>
  <div class="grp">
    <select id="method"><option value="cv">cv</option><option value="vision">vision</option><option value="hybrid">hybrid</option></select>
    <button id="auto">自動推定</button>
  </div>
  <div class="grp">
    <button id="addvp">消失点+（水平）</button>
    <button id="addvpv">消失点+（鉛直）</button>
    <button id="addchar">人物垂直線+</button>
    <button id="del" class="warn">選択を削除</button>
  </div>
  <div class="grp">
    <label class="chk"><input id="snap" type="checkbox" checked>消失点を地平線へスナップ</label>
    <span id="hint">ガイド密度</span>
    <input id="density" type="range" min="3" max="40" value="14">
    <span id="dval" class="pill">14</span>
  </div>
  <div class="grp">
    <button id="save" class="pri">保存</button>
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
<div id="wrap"><canvas id="cv"></canvas><div id="msg">画像パスを入れて「開く」。アイレベル/消失点をドラッグ。空白部ドラッグでアイレベル移動。</div></div>

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
  vps:[],                        // {x,y,vertical}
  chars:[],                      // {name, head:{x,y}, foot:{x,y}}
  density:14, snap:true,
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
function drawFan(vx,vy,r,density){
  const inside = vx>=r.x0&&vx<=r.x1&&vy>=r.y0&&vy<=r.y1;
  let amin,amax;
  if(inside){amin=0;amax=Math.PI*2;}
  else{
    let angs=[[r.x0,r.y0],[r.x1,r.y0],[r.x1,r.y1],[r.x0,r.y1]].map(c=>Math.atan2(c[1]-vy,c[0]-vx));
    amin=Math.min(...angs);amax=Math.max(...angs);
    if(amax-amin>Math.PI){angs=angs.map(a=>a<0?a+2*Math.PI:a);amin=Math.min(...angs);amax=Math.max(...angs);}
  }
  const big=(r.x1-r.x0)+(r.y1-r.y0);
  ctx.beginPath();
  for(let k=0;k<=density;k++){
    const a=amin+(amax-amin)*k/Math.max(1,density);
    const seg=clipSeg(vx,vy,vx+Math.cos(a)*big*3,vy+Math.sin(a)*big*3,r);
    if(seg){ctx.moveTo(seg[0],seg[1]);ctx.lineTo(seg[2],seg[3]);}
  }
  ctx.stroke();
}
function cross(x,y,col,rad){
  ctx.strokeStyle=col;ctx.lineWidth=2;
  ctx.beginPath();ctx.moveTo(x-rad,y);ctx.lineTo(x+rad,y);ctx.moveTo(x,y-rad);ctx.lineTo(x,y+rad);ctx.stroke();
  ctx.beginPath();ctx.arc(x,y,rad,0,Math.PI*2);ctx.stroke();
}
function dot(x,y,col,rad){ctx.fillStyle=col;ctx.beginPath();ctx.arc(x,y,rad,0,Math.PI*2);ctx.fill();}
function label(x,y,t,col){ctx.font='13px system-ui';ctx.lineWidth=3;ctx.strokeStyle='rgba(0,0,0,.85)';ctx.strokeText(t,x,y);ctx.fillStyle=col;ctx.fillText(t,x,y);}

function draw(){
  ctx.clearRect(0,0,cv.clientWidth,cv.clientHeight);
  if(!S.img){return;}
  const r=imgRect();
  ctx.drawImage(S.img,r.x0,r.y0,r.x1-r.x0,r.y1-r.y0);
  // パースガイド（薄く）
  ctx.save();ctx.globalAlpha=0.5;
  S.vps.forEach(v=>{const [sx,sy]=n2s(v.x,v.y);ctx.strokeStyle=C.GUIDE;ctx.lineWidth=1;drawFan(sx,sy,r,S.density);});
  ctx.restore();
  // アイレベル
  const [ax,ay]=n2s(0,S.horizon.ya), [bx,by]=n2s(1,S.horizon.yb);
  const seg=clipSeg(ax,ay,bx,by,r);
  if(seg){ctx.strokeStyle=C.EYE;ctx.lineWidth=2.5;ctx.beginPath();ctx.moveTo(seg[0],seg[1]);ctx.lineTo(seg[2],seg[3]);ctx.stroke();
    label(seg[0]+6,seg[1]-6,'EYE LEVEL / アイレベル',C.EYE);}
  // 消失点
  S.vps.forEach((v,i)=>{const [sx,sy]=n2s(v.x,v.y);const col=v.vertical?C.VPV:C.VP;
    cross(sx,sy,col,8);label(sx+11,sy-9,(v.vertical?'VVP':'VP')+(i+1),col);
    if(S.sel&&S.sel.type==='vp'&&S.sel.i===i){ctx.strokeStyle=C.SEL;ctx.lineWidth=1;ctx.beginPath();ctx.arc(sx,sy,13,0,Math.PI*2);ctx.stroke();}});
  // 人物の垂直線
  S.chars.forEach((c,i)=>{
    const [hx,hy]=n2s(c.head.x,c.head.y), [fx,fy]=n2s(c.foot.x,c.foot.y);
    // 真の鉛直（足元接地点を通る）
    ctx.strokeStyle=C.VERT;ctx.lineWidth=2.5;ctx.beginPath();
    ctx.moveTo(fx,Math.min(hy,fy)-Math.abs(fy-hy)*0.12-6);ctx.lineTo(fx,Math.max(hy,fy)+6);ctx.stroke();
    // 体軸（頭→足）破線
    ctx.strokeStyle=C.AXIS;ctx.lineWidth=2;ctx.setLineDash([10,7]);ctx.beginPath();ctx.moveTo(hx,hy);ctx.lineTo(fx,fy);ctx.stroke();ctx.setLineDash([]);
    dot(hx,hy,C.AXIS,5);dot(fx,fy,C.VERT,5);
    label(fx+7,hy-8,c.name||('人物'+letter(i)),C.VERT);
    if(S.sel&&S.sel.type==='char'&&S.sel.i===i){ctx.strokeStyle=C.SEL;ctx.lineWidth=1;
      ctx.strokeRect(Math.min(hx,fx)-8,Math.min(hy,fy)-8,Math.abs(fx-hx)+16,Math.abs(fy-hy)+16);}
  });
}

// ---- ヒットテスト ----
function near(sx,sy,px,py,th){return Math.hypot(sx-px,sy-py)<=th;}
function hit(mx,my){
  const th=10;
  for(let i=0;i<S.chars.length;i++){const c=S.chars[i];
    let p=n2s(c.head.x,c.head.y); if(near(mx,my,p[0],p[1],th))return{type:'char',i,sub:'head'};
    p=n2s(c.foot.x,c.foot.y); if(near(mx,my,p[0],p[1],th))return{type:'char',i,sub:'foot'};}
  for(let i=0;i<S.vps.length;i++){const p=n2s(S.vps[i].x,S.vps[i].y); if(near(mx,my,p[0],p[1],12))return{type:'vp',i};}
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

function clampN(v){return Math.max(-2,Math.min(3,v));}
function applySnap(){ if(S.snap){S.vps.forEach(v=>{if(!v.vertical)v.y=horizonYat(v.x);});} }

// ---- マウス ----
let dragStart=null;
cv.addEventListener('mousedown',e=>{
  if(!S.img)return; const m=mouse(e);
  const h=hit(m.x,m.y);
  S.sel = (h&&(h.type==='vp'||h.type==='char'))?{type:h.type,i:h.i}:S.sel;
  if(h){S.drag=h; dragStart={m, horizon:{...S.horizon}};}
  else{S.drag={type:'horizon',sub:'body'}; dragStart={m,horizon:{...S.horizon}}; S.sel=null;}
  draw();
});
window.addEventListener('mousemove',e=>{
  if(!S.drag||!S.img)return; const m=mouse(e); const [nx,ny]=s2n(m.x,m.y);
  const d=S.drag;
  if(d.type==='vp'){const v=S.vps[d.i]; v.x=clampN(nx); v.y=(S.snap&&!v.vertical)?horizonYat(v.x):clampN(ny);}
  else if(d.type==='char'){const c=S.chars[d.i]; c[d.sub].x=clampN(nx); c[d.sub].y=clampN(ny);}
  else if(d.type==='horizon'){
    if(d.sub==='a'){S.horizon.ya=clampN(ny);}
    else if(d.sub==='b'){S.horizon.yb=clampN(ny);}
    else{const dy=(m.y-dragStart.m.y)/(S.ih*S.view.scale); S.horizon.ya=clampN(dragStart.horizon.ya+dy); S.horizon.yb=clampN(dragStart.horizon.yb+dy);}
    applySnap();
  }
  draw();
});
window.addEventListener('mouseup',()=>{S.drag=null;dragStart=null;});
function mouse(e){const r=cv.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top};}
window.addEventListener('keydown',e=>{if((e.key==='Delete'||e.key==='Backspace')&&S.sel)delSel();});

// ---- 操作 ----
function setMsg(t){$('msg').textContent=t;}
async function openPath(){
  const path=$('path').value.trim(); if(!path){setMsg('パスを入力してください');return;}
  setMsg('読込中…');
  const r=await fetch('/api/open?path='+encodeURIComponent(path));
  const j=await r.json(); if(!r.ok){setMsg('エラー: '+(j.error||r.status));return;}
  const img=new Image();
  img.onload=()=>{S.img=img;S.iw=j.width;S.ih=j.height;S.path=j.path;S.name=j.name;
    S.horizon={ya:0.5,yb:0.5};S.vps=[];S.chars=[];S.sel=null;
    $('info').textContent=`${j.name}  ${j.width}×${j.height}`;
    fitView();draw();setMsg('読込完了。アイレベル/消失点を配置、または「自動推定」。');};
  img.onerror=()=>setMsg('画像の表示に失敗');
  img.src='/image?path='+encodeURIComponent(j.path);
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
  S.vps=(j.vanishing_points||[]).map(v=>({x:v.x,y:v.y,vertical:(v.axis==='vertical')}));
  S.chars=(j.characters||[]).map((c,i)=>({name:c.name||('人物'+letter(i)),head:{x:c.head[0],y:c.head[1]},foot:{x:c.foot[0],y:c.foot[1]}}));
  applySnap();draw();
}
function annotation(){
  return {method:'edit', image:{path:S.path,width:S.iw,height:S.ih},
    eye_level:{a:[0,S.horizon.ya],b:[1,S.horizon.yb]},
    vanishing_points:S.vps.map((v,i)=>({x:v.x,y:v.y,label:(v.vertical?'VVP':'VP')+(i+1),axis:v.vertical?'vertical':'horizontal'})),
    characters:S.chars.map((c,i)=>({name:c.name||('人物'+letter(i)),head:[c.head.x,c.head.y],foot:[c.foot.x,c.foot.y]})),
    notes:'editor'};
}
async function save(){
  if(!S.path){setMsg('先に画像を開いてください');return;}
  const r=await fetch('/api/save',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({path:S.path,annotation:annotation()})});
  const j=await r.json(); if(!r.ok){setMsg('保存エラー: '+(j.error||r.status));return;}
  setMsg('保存: '+(j.png||j.json)+(j.png_error?(' (PNG失敗:'+j.png_error+')'):''));
}
function addVP(vertical){const x=0.5,y=vertical?0.12:horizonYat(0.5);S.vps.push({x,y,vertical});S.sel={type:'vp',i:S.vps.length-1};draw();}
function addChar(){const i=S.chars.length;S.chars.push({name:'人物'+letter(i),head:{x:0.45,y:0.35},foot:{x:0.45,y:0.85}});S.sel={type:'char',i};draw();}
function delSel(){if(!S.sel)return;if(S.sel.type==='vp')S.vps.splice(S.sel.i,1);if(S.sel.type==='char')S.chars.splice(S.sel.i,1);S.sel=null;draw();}
function reset(){S.horizon={ya:0.5,yb:0.5};S.vps=[];S.chars=[];S.sel=null;draw();setMsg('リセットしました');}

$('open').onclick=openPath;
$('path').addEventListener('keydown',e=>{if(e.key==='Enter')openPath();});
$('auto').onclick=auto;
$('addvp').onclick=()=>addVP(false);
$('addvpv').onclick=()=>addVP(true);
$('addchar').onclick=addChar;
$('del').onclick=delSel;
$('save').onclick=save;
$('reset').onclick=reset;
$('snap').onchange=e=>{S.snap=e.target.checked;applySnap();draw();};
$('density').oninput=e=>{S.density=+e.target.value;$('dval').textContent=e.target.value;draw();};
window.addEventListener('resize',resize);
resize();
fetch('/api/config').then(r=>r.json()).then(j=>{if(j.image){$('path').value=j.image;openPath();}});
</script>
</body></html>
"""


if __name__ == "__main__":
    raise SystemExit(main())

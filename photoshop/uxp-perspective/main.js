/*
 * パース線 — Photoshop UXP プラグイン（最小プロトタイプ）
 *
 * 現在開いている PSD を背景に、アイレベル・消失点・人物垂直線を手で置き、
 * 「パース線をレイヤーに追加」で透過のパース線を新規レイヤーとして PSD に挿入する。
 * 自動推定・保存/ダウンロードは無し（Web版エディタ src/genzu_fix/perspective_editor.py 参照）。
 *
 * 注意: このリポジトリには Photoshop が無いため実機未検証。UXP の公式 API
 *  (require("photoshop") の imaging / core / action) に沿って書いている。PS の
 *  バージョンによって API 引数が変わることがあるので、動かない時は README を参照。
 *
 * 座標はすべて正規化 [0,1]（x=横/幅, y=縦/高さ）。線はベクトル定義なので、
 * 背景プレビューが縮小されていてもレイヤー出力はドキュメント原寸で正確に描ける。
 */
"use strict";

const C = { EYE:'#00c8ff', VP:'#ff28c8', VPV:'#ffb400', VERT:'#28dc46', AXIS:'#ffa000', GUIDE:'#ff78d2', SEL:'#ffffff' };

const cv = document.getElementById('cv');
const ctx = cv.getContext('2d');
const $ = id => document.getElementById(id);

const S = {
  bg:null,            // 背景プレビュー用 offscreen canvas（縮小可）
  docW:0, docH:0,     // ドキュメント原寸（レイヤー出力用）
  view:{scale:1, ox:0, oy:0},
  horizon:{ya:0.5, yb:0.5},
  vps:[],             // {x,y,vertical}
  chars:[],           // {head:{x,y}, foot:{x,y}}
  density:14, snap:true, lw:4,
  sel:null, drag:null,
};

function letter(i){let s='',n=i+1;while(n>0){let r=(n-1)%26;s=String.fromCharCode(65+r)+s;n=Math.floor((n-1)/26);}return s;}
function horizonYat(nx){return S.horizon.ya + (S.horizon.yb - S.horizon.ya)*nx;}
function setMsg(t){$('msg').textContent=t;}

// ---- 座標変換（ドキュメント原寸 docW/docH を表示キャンバスへフィット）----
function fitView(){
  const w=cv.clientWidth, h=cv.clientHeight;
  if(!S.docW){S.view={scale:1,ox:0,oy:0};return;}
  const pad=12, sc=Math.min((w-pad*2)/S.docW,(h-pad*2)/S.docH);
  S.view.scale=sc; S.view.ox=(w-S.docW*sc)/2; S.view.oy=(h-S.docH*sc)/2;
}
function n2s(nx,ny){return [S.view.ox+nx*S.docW*S.view.scale, S.view.oy+ny*S.docH*S.view.scale];}
function s2n(sx,sy){return [(sx-S.view.ox)/(S.docW*S.view.scale),(sy-S.view.oy)/(S.docH*S.view.scale)];}
function imgRect(){return {x0:S.view.ox,y0:S.view.oy,x1:S.view.ox+S.docW*S.view.scale,y1:S.view.oy+S.docH*S.view.scale};}

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

// ---- 描画（target ctx に対して。display=表示用 / 出力は renderLines で原寸）----
function drawFan(x,vx,vy,r,density){
  const inside = vx>=r.x0&&vx<=r.x1&&vy>=r.y0&&vy<=r.y1;
  let amin,amax;
  if(inside){amin=0;amax=Math.PI*2;}
  else{
    let angs=[[r.x0,r.y0],[r.x1,r.y0],[r.x1,r.y1],[r.x0,r.y1]].map(c=>Math.atan2(c[1]-vy,c[0]-vx));
    amin=Math.min.apply(null,angs);amax=Math.max.apply(null,angs);
    if(amax-amin>Math.PI){angs=angs.map(a=>a<0?a+2*Math.PI:a);amin=Math.min.apply(null,angs);amax=Math.max.apply(null,angs);}
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

// 共通の線描画。x=ctx, P=正規化→px, r=矩形, sc=線幅倍率, opt={withHandles}
function drawAnnotations(x, P, r, sc, opt){
  opt = opt || {};
  const LW=Math.max(1.5,S.lw*sc), GW=Math.max(1,LW*0.5), CR=(6+S.lw*1.4)*sc, DR=(3+S.lw*0.9)*sc;
  const FS=Math.max(11,Math.round((12+S.lw*1.6)*sc));
  const lbl=(px,py,t,col)=>{x.font=FS+'px sans-serif';x.lineWidth=Math.max(3,LW);x.strokeStyle='rgba(0,0,0,.85)';x.strokeText(t,px,py);x.fillStyle=col;x.fillText(t,px,py);};
  // ガイド
  x.save();x.globalAlpha=0.6;x.strokeStyle=C.GUIDE;x.lineWidth=GW;
  S.vps.forEach(v=>{const p=P(v.x,v.y);drawFan(x,p[0],p[1],r,S.density);});
  x.restore();
  // 傾け中の水平基準線（表示時のみ）
  if(opt.withHandles && S.drag && S.drag.type==='horizon' && S.drag.rotating){
    const my=(S.drag.pivotN?S.drag.pivotN.y:(S.horizon.ya+S.horizon.yb)/2);
    const sy=P(0,my)[1];
    x.save();x.globalAlpha=0.45;x.strokeStyle='#ffffff';x.lineWidth=Math.max(1,LW*0.6);
    x.setLineDash([12,8]);x.beginPath();x.moveTo(r.x0,sy);x.lineTo(r.x1,sy);x.stroke();x.setLineDash([]);x.restore();
    lbl(r.x0+6,sy-6,'水平(0°)','#ffffff');
  }
  // アイレベル
  const a=P(0,S.horizon.ya), b=P(1,S.horizon.yb);
  const seg=clipSeg(a[0],a[1],b[0],b[1],r);
  if(seg){x.strokeStyle=C.EYE;x.lineWidth=LW;x.beginPath();x.moveTo(seg[0],seg[1]);x.lineTo(seg[2],seg[3]);x.stroke();
    lbl(seg[0]+6*sc,seg[1]-6*sc,'EYE LEVEL / アイレベル',C.EYE);}
  // 消失点
  S.vps.forEach((v,i)=>{const p=P(v.x,v.y);const col=v.vertical?C.VPV:C.VP;
    x.strokeStyle=col;x.lineWidth=LW;
    x.beginPath();x.moveTo(p[0]-CR,p[1]);x.lineTo(p[0]+CR,p[1]);x.moveTo(p[0],p[1]-CR);x.lineTo(p[0],p[1]+CR);x.stroke();
    x.beginPath();x.arc(p[0],p[1],CR,0,Math.PI*2);x.stroke();
    lbl(p[0]+CR+4*sc,p[1]-CR,(v.vertical?'VVP':'VP')+(i+1),col);
    if(opt.withHandles && S.sel&&S.sel.type==='vp'&&S.sel.i===i){x.strokeStyle=C.SEL;x.lineWidth=Math.max(1,LW*0.5);x.beginPath();x.arc(p[0],p[1],CR+5,0,Math.PI*2);x.stroke();}});
  // 人物の垂直線
  S.chars.forEach((c2,i)=>{const h=P(c2.head.x,c2.head.y), f=P(c2.foot.x,c2.foot.y);
    x.strokeStyle=C.VERT;x.lineWidth=LW;x.beginPath();
    x.moveTo(f[0],Math.min(h[1],f[1])-Math.abs(f[1]-h[1])*0.12-6*sc);x.lineTo(f[0],Math.max(h[1],f[1])+6*sc);x.stroke();
    x.strokeStyle=C.AXIS;x.lineWidth=Math.max(1.5,LW*0.8);x.setLineDash([10*sc,7*sc]);x.beginPath();x.moveTo(h[0],h[1]);x.lineTo(f[0],f[1]);x.stroke();x.setLineDash([]);
    x.fillStyle=C.AXIS;x.beginPath();x.arc(h[0],h[1],DR,0,Math.PI*2);x.fill();
    x.fillStyle=C.VERT;x.beginPath();x.arc(f[0],f[1],DR,0,Math.PI*2);x.fill();
    lbl(f[0]+DR+3*sc,h[1]-8*sc,'人物'+letter(i),C.VERT);
    if(opt.withHandles && S.sel&&S.sel.type==='char'&&S.sel.i===i){x.strokeStyle=C.SEL;x.lineWidth=Math.max(1,LW*0.5);
      x.strokeRect(Math.min(h[0],f[0])-8,Math.min(h[1],f[1])-8,Math.abs(f[0]-h[0])+16,Math.abs(f[1]-h[1])+16);}});
}

function draw(){
  ctx.clearRect(0,0,cv.clientWidth,cv.clientHeight);
  if(!S.docW){return;}
  const r=imgRect();
  if(S.bg) ctx.drawImage(S.bg, r.x0,r.y0, r.x1-r.x0, r.y1-r.y0);
  drawAnnotations(ctx, n2s, r, 1, {withHandles:true});
}

function resize(){
  const dpr=Math.max(1,window.devicePixelRatio||1);
  cv.width=cv.clientWidth*dpr; cv.height=cv.clientHeight*dpr;
  ctx.setTransform(dpr,0,0,dpr,0,0);
  if(S.docW) fitView();
  draw();
}

// ---- ヒットテスト / 操作（Web版から移植）----
function near(sx,sy,px,py,th){return Math.hypot(sx-px,sy-py)<=th;}
function distToSeg(px,py,x0,y0,x1,y1){const dx=x1-x0,dy=y1-y0,l2=dx*dx+dy*dy;
  let t=l2?((px-x0)*dx+(py-y0)*dy)/l2:0; t=Math.max(0,Math.min(1,t));
  return Math.hypot(px-(x0+t*dx),py-(y0+t*dy));}
function hit(mx,my){
  const th=11;
  for(let i=0;i<S.chars.length;i++){const c=S.chars[i];
    let p=n2s(c.head.x,c.head.y); if(near(mx,my,p[0],p[1],th))return{type:'char',i,sub:'head'};
    p=n2s(c.foot.x,c.foot.y); if(near(mx,my,p[0],p[1],th))return{type:'char',i,sub:'foot'};}
  for(let i=0;i<S.vps.length;i++){const p=n2s(S.vps[i].x,S.vps[i].y); if(near(mx,my,p[0],p[1],13))return{type:'vp',i};}
  const a=n2s(0,S.horizon.ya), b=n2s(1,S.horizon.yb);
  if(near(mx,my,a[0],a[1],th))return{type:'horizon',sub:'a'};
  if(near(mx,my,b[0],b[1],th))return{type:'horizon',sub:'b'};
  if(distToSeg(mx,my,a[0],a[1],b[0],b[1])<8)return{type:'horizon',sub:'body'};
  return null;
}
function clampN(v){return Math.max(-2,Math.min(3,v));}
function clampW(v){return Math.max(-12,Math.min(12,v));}
function applySnap(){ if(S.snap){S.vps.forEach(v=>{if(!v.vertical)v.y=horizonYat(v.x);});} }
function rotPt(sx,sy,Ps,c,s){const dx=sx-Ps[0],dy=sy-Ps[1];return [Ps[0]+dx*c-dy*s, Ps[1]+dx*s+dy*c];}
function rotateHorizon(delta,Ps){
  const c=Math.cos(delta),s=Math.sin(delta);
  let A=n2s(0,S.horizon.ya), B=n2s(1,S.horizon.yb);
  A=rotPt(A[0],A[1],Ps,c,s); B=rotPt(B[0],B[1],Ps,c,s);
  const r=imgRect();
  const dx=B[0]-A[0], m=Math.abs(dx)<1e-6?0:(B[1]-A[1])/dx;
  const yl=A[1]+m*(r.x0-A[0]), yr=A[1]+m*(r.x1-A[0]);
  const nyl=s2n(r.x0,yl)[1], nyr=s2n(r.x1,yr)[1];
  if(Math.abs(nyr-nyl)>1.5) return;
  const degNow=Math.abs(Math.atan2(yr-yl,r.x1-r.x0)*180/Math.PI);
  if(degNow<1.0){const mid=(nyl+nyr)/2;S.horizon.ya=clampN(mid);S.horizon.yb=clampN(mid);}
  else{S.horizon.ya=clampN(nyl); S.horizon.yb=clampN(nyr);}
  S.vps.forEach(v=>{const sp=n2s(v.x,v.y);const rp=rotPt(sp[0],sp[1],Ps,c,s);const np=s2n(rp[0],rp[1]);v.x=clampW(np[0]);v.y=clampW(np[1]);});
}
function mouse(e){const r=cv.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top};}

cv.addEventListener('mousedown',e=>{
  if(!S.docW)return; const m=mouse(e); const h=hit(m.x,m.y);
  S.sel = (h&&(h.type==='vp'||h.type==='char'))?{type:h.type,i:h.i}:S.sel;
  S.drag = h || {type:'horizon',sub:'body'};
  if(!h) S.sel=null;
  S.drag.lastY=m.y; S.drag.lastX=m.x; S.drag.rotating=false;
  draw();
});
window.addEventListener('mousemove',e=>{
  if(!S.drag||!S.docW)return; const m=mouse(e); const nn=s2n(m.x,m.y); const nx=nn[0],ny=nn[1]; const d=S.drag;
  if(d.type==='vp'){const v=S.vps[d.i]; v.x=clampW(nx); v.y=(S.snap&&!v.vertical)?horizonYat(v.x):clampW(ny);}
  else if(d.type==='char'){const c=S.chars[d.i]; c[d.sub].x=clampN(nx); c[d.sub].y=clampN(ny);}
  else if(d.type==='horizon'){
    if(d.sub==='a'){S.horizon.ya=clampN(ny);applySnap();}
    else if(d.sub==='b'){S.horizon.yb=clampN(ny);applySnap();}
    else{
      const r=imgRect();
      const inside = m.x>=r.x0&&m.x<=r.x1&&m.y>=r.y0&&m.y<=r.y1;
      if(inside){
        const dy=(m.y-d.lastY)/(S.docH*S.view.scale);
        S.horizon.ya=clampN(S.horizon.ya+dy); S.horizon.yb=clampN(S.horizon.yb+dy);
        S.vps.forEach(v=>v.y=clampW(v.y+dy)); d.rotating=false; applySnap();
      } else {
        if(!d.rotating){d.rotating=true; d.pivotN={x:0.5,y:(S.horizon.ya+S.horizon.yb)/2}; d.prevAng=null;}
        const Ps=n2s(d.pivotN.x,d.pivotN.y);
        const ang=Math.atan2(m.y-Ps[1],m.x-Ps[0]);
        if(d.prevAng===null){d.prevAng=ang;}
        const delta=ang-d.prevAng; d.prevAng=ang;
        if(delta) rotateHorizon(delta,Ps); applySnap();
      }
    }
    d.lastY=m.y; d.lastX=m.x;
  }
  draw();
});
window.addEventListener('mouseup',()=>{S.drag=null;});
window.addEventListener('keydown',e=>{if((e.key==='Delete'||e.key==='Backspace')&&S.sel)delSel();});

function addVP(vertical){const x=0.5,y=vertical?0.12:horizonYat(0.5);S.vps.push({x:x,y:y,vertical:vertical});S.sel={type:'vp',i:S.vps.length-1};draw();}
function addChar(){const i=S.chars.length;S.chars.push({head:{x:0.45,y:0.35},foot:{x:0.45,y:0.85}});S.sel={type:'char',i:i};draw();}
function delSel(){if(!S.sel)return;if(S.sel.type==='vp')S.vps.splice(S.sel.i,1);if(S.sel.type==='char')S.chars.splice(S.sel.i,1);S.sel=null;draw();}
function reset(){S.horizon={ya:0.5,yb:0.5};S.vps=[];S.chars=[];S.sel=null;draw();setMsg('リセットしました');}

// ===========================================================================
// Photoshop 連携
// ===========================================================================
function ps(){ return require("photoshop"); }

// 現在ドキュメントを読み込み、背景プレビュー(縮小)を作る。原寸は docW/docH に保持。
async function loadDoc(){
  let photoshop;
  try{ photoshop = ps(); }catch(e){ setMsg('Photoshop API を取得できません（PS外で実行中？）'); return; }
  const app = photoshop.app, imaging = photoshop.imaging, core = photoshop.core;
  const doc = app.activeDocument;
  if(!doc){ setMsg('開いているドキュメントがありません'); return; }
  setMsg('ドキュメント読込中…');
  try{
    S.docW = doc.width; S.docH = doc.height;
    // 表示プレビューは長辺 ~1600px に縮小（重い原寸をそのまま描かない）
    const maxPrev = 1600;
    const opts = { documentID: doc.id, componentSize: 8, applyAlpha: false };
    if(Math.max(S.docW,S.docH) > maxPrev){
      const k = maxPrev/Math.max(S.docW,S.docH);
      opts.targetSize = { width: Math.round(S.docW*k), height: Math.round(S.docH*k) };
    }
    let result;
    await core.executeAsModal(async ()=>{ result = await imaging.getPixels(opts); },
      {commandName:'ドキュメント読込'});
    const id = result.imageData;
    const w = id.width, h = id.height, comps = id.components;
    const buf = await id.getData({chunky:true});
    id.dispose && id.dispose();
    // RGBA の ImageData を作る（comps=3 のときは alpha=255 を補う）
    const out = new Uint8ClampedArray(w*h*4);
    for(let i=0,p=0;i<w*h;i++){
      out[i*4]   = buf[p++];
      out[i*4+1] = buf[p++];
      out[i*4+2] = buf[p++];
      out[i*4+3] = comps===4 ? buf[p++] : 255;
    }
    const off = document.createElement('canvas'); off.width=w; off.height=h;
    off.getContext('2d').putImageData(new ImageData(out,w,h),0,0);
    S.bg = off;
    $('info').textContent = doc.name + '  ' + S.docW + '×' + S.docH;
    fitView(); draw();
    setMsg('読込完了。アイレベル/消失点を配置 → 「パース線をレイヤーに追加」。');
  }catch(e){ setMsg('読込失敗: '+(e&&e.message?e.message:e)); }
}

// 原寸の透過キャンバスにパース線だけを描く（レイヤー出力用）
function renderLinesFull(){
  const W=S.docW, H=S.docH;
  const c=document.createElement('canvas'); c.width=W; c.height=H;
  const x=c.getContext('2d');
  const sc = 1/Math.max(S.view.scale,1e-6);   // 表示→原寸 の線幅倍率
  const P=(nx,ny)=>[nx*W,ny*H];
  const r={x0:0,y0:0,x1:W,y1:H};
  drawAnnotations(x, P, r, sc, {withHandles:false});
  return x.getImageData(0,0,W,H);  // RGBA
}

// パース線を新規レイヤーとして現在ドキュメントに挿入
async function addLayer(){
  if(!S.docW){ setMsg('先にドキュメントを読み込んでください'); return; }
  let photoshop;
  try{ photoshop = ps(); }catch(e){ setMsg('Photoshop API を取得できません'); return; }
  const app = photoshop.app, imaging = photoshop.imaging, core = photoshop.core, action = photoshop.action;
  setMsg('パース線レイヤーを生成中…');
  try{
    const imgData = renderLinesFull();                 // 原寸 RGBA
    const buffer = new Uint8Array(imgData.data.buffer); // Uint8ClampedArray → Uint8Array
    const W=S.docW, H=S.docH;
    await core.executeAsModal(async ()=>{
      const doc = app.activeDocument;
      // 新規レイヤーを作成
      await action.batchPlay([{ _obj:'make', _target:[{_ref:'layer'}],
        _options:{ dialogOptions:'dontDisplay' } }], {});
      const layer = doc.activeLayers[0];
      try{ layer.name = 'AI原図修正/パース線'; }catch(_e){}
      const psImageData = await imaging.createImageDataFromBuffer(buffer,
        { width:W, height:H, components:4, componentSize:8, colorSpace:'RGB', chunky:true });
      await imaging.putPixels({ documentID:doc.id, layerID:layer.id, imageData:psImageData });
      psImageData.dispose && psImageData.dispose();
    }, { commandName:'パース線をレイヤーに追加' });
    setMsg('「AI原図修正/パース線」レイヤーを追加しました。');
  }catch(e){ setMsg('レイヤー追加失敗: '+(e&&e.message?e.message:e)); }
}

// ---- 配線 ----
$('loaddoc').onclick = loadDoc;
$('addvp').onclick = ()=>addVP(false);
$('addvpv').onclick = ()=>addVP(true);
$('addchar').onclick = addChar;
$('del').onclick = delSel;
$('addlayer').onclick = addLayer;
$('reset').onclick = reset;
$('snap').onchange = e=>{S.snap=e.target.checked;applySnap();draw();};
$('density').oninput = e=>{S.density=+e.target.value;draw();};
$('lw').oninput = e=>{S.lw=+e.target.value;draw();};
window.addEventListener('resize', resize);
resize();

// 3Dステージ 簡易ビューワー (編集不可・カメラ操作+スクショのみ)
// esbuild で IIFE にバンドルし、GLB(base64) と共に単一HTMLへ埋め込む。
// HTML 側で window.__GLB_B64 と window.__VIEWER_CFG を定義しておくこと。
//
// __VIEWER_CFG = {
//   title: 'タイトル',
//   exposure: 1.0,
//   background: '#17120d',
//   fog: { color: '#e8ece9', near: 10, far: 90 },      // 省略可
//   presets: { A: {pos:[x,y,z], tgt:[x,y,z], label:'かまど側'}, ... },
//   lights: [
//     { type:'hemi', sky:'#fff1dd', ground:'#2e2418', i:0.35 },
//     { type:'point', p:[x,y,z], c:'#fff2d8', i:9, shadow:true },
//     { type:'dir', p:[x,y,z], tgt:[x,y,z], c:'#ffffff', i:3, shadow:true },
//   ],
// }
// ※座標は three.js 系 (Blender の (x,y,z) → (x, z, -y))
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const CFG = window.__VIEWER_CFG || {};
const TITLE = CFG.title || '3Dステージ';

// ---------- renderer / scene ----------
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = CFG.exposure ?? 1.0;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(CFG.background || '#17120d');
if (CFG.fog) scene.fog = new THREE.Fog(CFG.fog.color, CFG.fog.near, CFG.fog.far);

const camera = new THREE.PerspectiveCamera(46, window.innerWidth / window.innerHeight, 0.05, 500);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.12;

const PRESETS = CFG.presets || {
  A: { pos: [5.55, 1.4, -0.55], tgt: [1.35, 1.15, -4.05], label: '視点A' },
};
function applyPreset(k) {
  const p = PRESETS[k];
  camera.position.set(...p.pos);
  controls.target.set(...p.tgt);
  controls.update();
  if (typeof syncEyeUI === 'function') syncEyeUI();
  fisheyeState.on = false;
  if (p.mm) setFov((360 / Math.PI) * Math.atan(21.6 / p.mm));
}

// ---------- lights ----------
const LIGHTS = CFG.lights || [
  { type: 'hemi', sky: '#fff1dd', ground: '#2e2418', i: 0.35 },
  { type: 'point', p: [3.9, 1.7, -4.1], c: '#fff2d8', i: 9, shadow: true },
];
for (const d of LIGHTS) {
  let l;
  if (d.type === 'hemi') {
    l = new THREE.HemisphereLight(d.sky, d.ground, d.i);
  } else if (d.type === 'dir') {
    l = new THREE.DirectionalLight(d.c, d.i);
    l.position.set(...d.p);
    if (d.tgt) {
      l.target.position.set(...d.tgt);
      scene.add(l.target);
    }
    if (d.shadow) {
      l.castShadow = true;
      l.shadow.bias = -0.002;
      l.shadow.mapSize.set(2048, 2048);
      const ext = d.shadowExtent ?? 20;
      l.shadow.camera.left = -ext; l.shadow.camera.right = ext;
      l.shadow.camera.top = ext; l.shadow.camera.bottom = -ext;
      l.shadow.camera.far = 300;
    }
  } else {
    l = new THREE.PointLight(d.c, d.i, 0, 2);
    l.position.set(...d.p);
    if (d.shadow) {
      l.castShadow = true;
      l.shadow.bias = -0.004;
      l.shadow.mapSize.set(1024, 1024);
    }
  }
  scene.add(l);
}

// ---------- load GLB ----------
const bin = Uint8Array.from(atob(window.__GLB_B64), (c) => c.charCodeAt(0));
new GLTFLoader().parse(bin.buffer, '', (gltf) => {
  gltf.scene.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true;
      o.receiveShadow = true;
      // 張りぼて(遠景ビルボード)は距離フォグの対象外にする。
      // 絵の中に霧が描き込まれているため、フォグを重ねると白飛びして見えなくなる。
      const nm = o.name || '';
      const pnm = (o.parent && o.parent.name) || '';
      if (nm.startsWith('mtn') || pnm.startsWith('mtn') || nm.startsWith('farwall') || pnm.startsWith('farwall')) {
        if (o.material) o.material.fog = false;
        o.castShadow = false;
      }
    }
  });
  scene.add(gltf.scene);
  applyPreset(Object.keys(PRESETS)[0]);
});

// ---------- 魚眼ポストパス (樽型歪み: 透視画像→等距離射影の近似) ----------
const fisheyeState = { on: false };
const rtSize = () => [innerWidth * renderer.getPixelRatio(), innerHeight * renderer.getPixelRatio()];
let rt = new THREE.WebGLRenderTarget(...rtSize());
const postCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
const postScene = new THREE.Scene();
const postMat = new THREE.ShaderMaterial({
  uniforms: {
    tex: { value: rt.texture },
    thetaMax: { value: 0.9 },
    aspect: { value: innerWidth / innerHeight },
  },
  vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }',
  fragmentShader: [
    'varying vec2 vUv;',
    'uniform sampler2D tex;',
    'uniform float thetaMax;',
    'uniform float aspect;',
    'void main(){',
    '  vec2 c = vUv * 2.0 - 1.0;',
    '  c.x *= aspect;',
    '  float maxR = length(vec2(aspect, 1.0));',
    '  float rn = length(c) / maxR;',
    '  float k = tan(thetaMax);',
    '  float rs = (rn < 1e-5) ? 0.0 : tan(rn * thetaMax) / k;',
    '  vec2 dir = (rn < 1e-5) ? vec2(0.0) : normalize(c);',
    '  vec2 src = dir * rs * maxR;',
    '  src.x /= aspect;',
    '  vec2 uv = (src + 1.0) * 0.5;',
    '  gl_FragColor = texture2D(tex, clamp(uv, 0.0, 1.0));',
    '  #include <colorspace_fragment>',  // RT経由でも出力色空間変換を適用 (暗くなるのを防ぐ)
    '}',
  ].join('\n'),
  depthTest: false,
});
postScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), postMat));

function renderFrame() {
  if (fisheyeState.on) {
    postMat.uniforms.thetaMax.value = (camera.fov * Math.PI) / 360;
    postMat.uniforms.aspect.value = camera.aspect;
    renderer.setRenderTarget(rt);
    renderer.render(scene, camera);
    renderer.setRenderTarget(null);
    renderer.render(postScene, postCam);
  } else {
    renderer.render(scene, camera);
  }
}

// ---------- UI ----------
const EYE_RANGE = CFG.eyeRange || [0.2, 6.0];
const ui = document.createElement('div');
ui.style.cssText =
  'position:fixed;top:12px;left:12px;z-index:10;background:rgba(20,15,10,.82);color:#f0e8dc;' +
  'padding:12px 14px;border-radius:10px;font:13px/1.7 sans-serif;user-select:none;max-width:280px';
ui.innerHTML =
  `<div style="font-weight:bold;margin-bottom:6px">${TITLE}</div>` +
  '<div id="btns" style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap"></div>' +
  '<div style="margin-bottom:2px">レンズ</div>' +
  '<div id="lens" style="display:flex;gap:5px;margin-bottom:4px"></div>' +
  '<label style="font-size:12px"><input type="checkbox" id="dolly" checked> 構図を保って切替(ドリー補正)</label><br>' +
  '<label>画角 <input id="fov" type="range" min="15" max="110" step="1" style="vertical-align:middle;width:110px"> ' +
  '<span id="fovv"></span>mm相当</label><br>' +
  '<label>アイレベル <input id="eye" type="range" step="0.05" style="vertical-align:middle;width:96px"> ' +
  '<span id="eyev"></span>m</label>' +
  '<div style="margin:6px 0 2px">左ドラッグの操作</div>' +
  '<div id="modes" style="display:flex;gap:5px;margin-bottom:6px"></div>' +
  '<div style="margin:8px 0"><button id="shot" style="width:100%;padding:7px;border:0;border-radius:7px;' +
  'background:#c96;color:#221;font-weight:bold;cursor:pointer">📷 スクリーンショット保存</button></div>' +
  '<div style="opacity:.75;font-size:12px">右ドラッグ: 平行移動 / ホイール: ズーム<br>WASD+QE: 移動</div>';
document.body.appendChild(ui);

const btnCss = 'flex:1;padding:6px 8px;border:0;border-radius:7px;background:#554636;color:#f0e8dc;cursor:pointer;white-space:nowrap';
const btns = ui.querySelector('#btns');
for (const k of Object.keys(PRESETS)) {
  const b = document.createElement('button');
  b.textContent = PRESETS[k].label || k;
  b.style.cssText = btnCss;
  b.onclick = () => applyPreset(k);
  btns.appendChild(b);
}

const fov = ui.querySelector('#fov');
const fovv = ui.querySelector('#fovv');
function fovToMm(deg) {
  return Math.round(21.6 / Math.tan((deg * Math.PI) / 360));
}
function setFov(deg) {
  camera.fov = Math.min(110, Math.max(15, deg));
  camera.updateProjectionMatrix();
  fov.value = camera.fov;
  fovv.textContent = fovToMm(camera.fov);
}
fov.oninput = () => {
  fisheyeState.on = false;  // スライダー操作は通常レンズ扱い
  setFov(+fov.value);
};
setFov(camera.fov);

// レンズプリセット。ドリー補正ON時は注視点の写る大きさを保ったままカメラが前後する
// (=単なるズームではなく、広角のパース誇張/望遠の圧縮が出る)
const lensRow = ui.querySelector('#lens');
function mmToFov(mm) {
  return (360 / Math.PI) * Math.atan(21.6 / mm);
}
function setLens(mm, fisheye = false) {
  const newFov = fisheye ? 100 : mmToFov(mm);
  const dolly = ui.querySelector('#dolly').checked;
  if (dolly && !fisheye) {
    const scale = Math.tan((camera.fov * Math.PI) / 360) / Math.tan((newFov * Math.PI) / 360);
    const off = new THREE.Vector3().subVectors(camera.position, controls.target);
    const d = off.length();
    let newD = d * scale;
    // ステージから飛び出さないよう制限: 距離60mまで・カメラは地上0.25m以上
    newD = Math.min(newD, 60);
    if (off.y < 0) {
      const maxD = (0.25 - controls.target.y) / (off.y / d);
      if (maxD > 0) newD = Math.min(newD, maxD);
    }
    off.setLength(newD);
    camera.position.copy(controls.target).add(off);
    controls.update();
    syncEyeUI();
  }
  fisheyeState.on = fisheye;
  setFov(newFov);
}
for (const [label, mm, fe] of [['魚眼', 0, true], ['広角', 24, false], ['標準', 50, false], ['望遠', 85, false]]) {
  const b = document.createElement('button');
  b.textContent = label;
  b.style.cssText = btnCss;
  b.onclick = () => setLens(mm, fe);
  lensRow.appendChild(b);
}

// アイレベル (カメラ高さを注視点ごと上下)
const eye = ui.querySelector('#eye');
const eyev = ui.querySelector('#eyev');
eye.min = EYE_RANGE[0];
eye.max = EYE_RANGE[1];
function syncEyeUI() {
  eye.value = camera.position.y;
  eyev.textContent = (+camera.position.y).toFixed(2);
}
eye.oninput = () => {
  const dy = +eye.value - camera.position.y;
  camera.position.y += dy;
  controls.target.y += dy;
  eyev.textContent = (+eye.value).toFixed(2);
};

// 操作モード: 周回(対象の周りを回る) / 見回し(その場で首を振る)
let mode = 'orbit';
const modeRow = ui.querySelector('#modes');
const modeBtns = {};
for (const [key, label] of [['orbit', '周回'], ['look', '見回し']]) {
  const b = document.createElement('button');
  b.textContent = label;
  b.style.cssText = btnCss;
  b.onclick = () => setMode(key);
  modeRow.appendChild(b);
  modeBtns[key] = b;
}
function setMode(m) {
  mode = m;
  controls.enableRotate = m === 'orbit';
  modeBtns.orbit.style.background = m === 'orbit' ? '#c96' : '#554636';
  modeBtns.orbit.style.color = m === 'orbit' ? '#221' : '#f0e8dc';
  modeBtns.look.style.background = m === 'look' ? '#c96' : '#554636';
  modeBtns.look.style.color = m === 'look' ? '#221' : '#f0e8dc';
}
setMode('orbit');

// 見回しモードのドラッグ処理 (カメラ位置を固定して注視点を回す)
const look = { drag: false, x: 0, y: 0 };
renderer.domElement.addEventListener('pointerdown', (e) => {
  if (mode === 'look' && e.button === 0) {
    look.drag = true;
    look.x = e.clientX;
    look.y = e.clientY;
  }
});
addEventListener('pointermove', (e) => {
  if (!look.drag) return;
  const dx = e.clientX - look.x;
  const dy = e.clientY - look.y;
  look.x = e.clientX;
  look.y = e.clientY;
  const off = new THREE.Vector3().subVectors(controls.target, camera.position);
  const sph = new THREE.Spherical().setFromVector3(off);
  sph.theta -= dx * 0.0035;
  sph.phi = Math.min(Math.PI - 0.05, Math.max(0.05, sph.phi - dy * 0.0035));
  sph.radius = 5;
  off.setFromSpherical(sph);
  controls.target.copy(camera.position).add(off);
  controls.update();
});
addEventListener('pointerup', () => { look.drag = false; });

ui.querySelector('#shot').onclick = () => {
  renderFrame();
  renderer.domElement.toBlob((blob) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    const t = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19);
    a.download = `stage_${t}.png`;
    a.click();
    URL.revokeObjectURL(a.href);
  }, 'image/png');
};

// ---------- WASD 移動 ----------
const keys = new Set();
addEventListener('keydown', (e) => keys.add(e.code));
addEventListener('keyup', (e) => keys.delete(e.code));

function moveCamera(dt) {
  const speed = (CFG.moveSpeed ?? 1.6) * dt;
  const fwd = new THREE.Vector3().subVectors(controls.target, camera.position);
  fwd.y = 0;
  fwd.normalize();
  const right = new THREE.Vector3(-fwd.z, 0, fwd.x);
  const d = new THREE.Vector3();
  if (keys.has('KeyW')) d.add(fwd);
  if (keys.has('KeyS')) d.sub(fwd);
  if (keys.has('KeyD')) d.add(right);
  if (keys.has('KeyA')) d.sub(right);
  if (keys.has('KeyE')) d.y += 1;
  if (keys.has('KeyQ')) d.y -= 1;
  if (d.lengthSq() > 0) {
    d.normalize().multiplyScalar(speed);
    camera.position.add(d);
    controls.target.add(d);
  }
}

addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  rt.setSize(...rtSize());
});

let prev = performance.now();
function loop(now) {
  const dt = Math.min((now - prev) / 1000, 0.1);
  prev = now;
  moveCamera(dt);
  controls.update();
  renderFrame();
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);

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
    }
  });
  scene.add(gltf.scene);
  applyPreset(Object.keys(PRESETS)[0]);
});

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
  '<div id="lens" style="display:flex;gap:5px;margin-bottom:6px"></div>' +
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
fov.oninput = () => setFov(+fov.value);
setFov(camera.fov);

// レンズプリセット (魚眼風は超広角の近似。実際の歪みはBlenderの魚眼カメラで)
const lensRow = ui.querySelector('#lens');
for (const [label, mm] of [['魚眼風', 14], ['広角', 24], ['標準', 50], ['望遠', 85]]) {
  const b = document.createElement('button');
  b.textContent = label;
  b.style.cssText = btnCss;
  b.onclick = () => setFov((360 / Math.PI) * Math.atan(21.6 / mm));
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
  renderer.render(scene, camera);
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
});

let prev = performance.now();
function loop(now) {
  const dt = Math.min((now - prev) / 1000, 0.1);
  prev = now;
  moveCamera(dt);
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);

// 尚善 3Dステージ 簡易ビューワー (編集不可・カメラ操作+スクショのみ)
// esbuild で IIFE にバンドルし、GLB(base64) と共に単一HTMLへ埋め込む。
// HTML 側で window.__GLB_B64 / window.__STAGE_TITLE を定義しておくこと。
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const TITLE = window.__STAGE_TITLE || '3Dステージ';

// ---------- renderer / scene ----------
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x17120d);

const camera = new THREE.PerspectiveCamera(46, window.innerWidth / window.innerHeight, 0.05, 100);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.12;

// Blender(Z-up) の座標 → three(Y-up):  (x, y, z) → (x, z, -y)
const PRESETS = {
  A: { pos: [5.55, 1.40, -0.55], tgt: [1.35, 1.15, -4.05], label: 'かまど側' },
  B: { pos: [0.75, 1.45, -3.75], tgt: [5.90, 1.05, -1.35], label: '入口側' },
  T: { pos: [3.20, 7.20, 2.80], tgt: [3.20, 0.30, -2.20], label: '俯瞰' },
};
function applyPreset(k) {
  const p = PRESETS[k];
  camera.position.set(...p.pos);
  controls.target.set(...p.tgt);
  controls.update();
}

// ---------- lights ----------
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
scene.add(new THREE.HemisphereLight(0xfff1dd, 0x2e2418, 0.35));
const lightDefs = [
  // 窓の外光 (N/W/S) — 影あり
  { p: [3.9, 1.7, -4.1], c: 0xfff2d8, i: 9, shadow: true },
  { p: [0.3, 1.7, -1.55], c: 0xfff2d8, i: 9, shadow: true },
  { p: [2.2, 1.7, -0.3], c: 0xfff2d8, i: 7, shadow: true },
  // 天井下の暖色フィル
  { p: [1.8, 2.3, -2.2], c: 0xffdfb0, i: 5 },
  { p: [4.6, 2.3, -2.2], c: 0xffdfb0, i: 5 },
];
for (const d of lightDefs) {
  const l = new THREE.PointLight(d.c, d.i, 0, 2);
  l.position.set(...d.p);
  if (d.shadow) {
    l.castShadow = true;
    l.shadow.bias = -0.004;
    l.shadow.mapSize.set(1024, 1024);
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
  applyPreset('A');
});

// ---------- UI ----------
const ui = document.createElement('div');
ui.style.cssText =
  'position:fixed;top:12px;left:12px;z-index:10;background:rgba(20,15,10,.82);color:#f0e8dc;' +
  'padding:12px 14px;border-radius:10px;font:13px/1.6 sans-serif;user-select:none;max-width:270px';
ui.innerHTML =
  `<div style="font-weight:bold;margin-bottom:6px">${TITLE}</div>` +
  '<div id="btns" style="display:flex;gap:6px;margin-bottom:8px"></div>' +
  '<label>画角 <input id="fov" type="range" min="20" max="70" step="1" style="vertical-align:middle;width:120px"> ' +
  '<span id="fovv"></span>mm相当</label>' +
  '<div style="margin:8px 0"><button id="shot" style="width:100%;padding:7px;border:0;border-radius:7px;' +
  'background:#c96;color:#221;font-weight:bold;cursor:pointer">📷 スクリーンショット保存</button></div>' +
  '<div style="opacity:.75;font-size:12px">左ドラッグ: 回転 / 右ドラッグ: 平行移動<br>' +
  'ホイール: ズーム / WASD+QE: 移動<br><span id="hint"></span></div>';
document.body.appendChild(ui);

const btns = ui.querySelector('#btns');
for (const k of Object.keys(PRESETS)) {
  const b = document.createElement('button');
  b.textContent = PRESETS[k].label;
  b.style.cssText = 'flex:1;padding:6px;border:0;border-radius:7px;background:#554636;color:#f0e8dc;cursor:pointer';
  b.onclick = () => applyPreset(k);
  btns.appendChild(b);
}

const fov = ui.querySelector('#fov');
const fovv = ui.querySelector('#fovv');
function fovToMm(deg) {
  // 35mm判換算 (対角) の近似表示
  return Math.round(21.6 / Math.tan((deg * Math.PI) / 360));
}
fov.value = camera.fov;
fovv.textContent = fovToMm(camera.fov);
fov.oninput = () => {
  camera.fov = +fov.value;
  camera.updateProjectionMatrix();
  fovv.textContent = fovToMm(camera.fov);
};

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
  const speed = 1.6 * dt;
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

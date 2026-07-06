const state = {
  sessionId: null,
  images: [],
  outputDir: "",
  modes: {}, // imageId -> "normal" | "fullbody"
  neckY: {}, // imageId -> 首位置（元画像のピクセル座標）
};

const KIND_LABELS = {
  normal: "整形",
  fb_upper: "上半身",
  fb_body: "首から下",
  fb_feet: "足元",
  fb_full: "全身",
};

const $ = (id) => document.getElementById(id);

function readValue(id, fallback = "") {
  const element = $(id);
  return element ? element.value.trim() : fallback;
}

function readNumber(id, fallback) {
  const parsed = Number(readValue(id, String(fallback)));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function readChecked(id, fallback = false) {
  const element = $(id);
  return element ? element.checked : fallback;
}

function selectedTargetSizes() {
  const checked = Array.from(document.querySelectorAll(".target-size-choice:checked"))
    .map((input) => input.value.trim())
    .filter(Boolean);
  const sizes = checked.length ? checked : ["1024x1024"];
  if (!checked.length) {
    const fallback = document.querySelector('.target-size-choice[value="1024x1024"]');
    if (fallback) fallback.checked = true;
  }
  $("targetSizes").value = sizes.join(", ");
  return $("targetSizes").value;
}

function setStatus(text) {
  $("serverStatus").textContent = text;
}

function setProgress(text, value = 0, indeterminate = false) {
  const bar = $("taskProgress");
  if (indeterminate) {
    bar.removeAttribute("value");
  } else {
    bar.value = Math.max(0, Math.min(100, value));
  }
  $("progressText").textContent = text;
}

function setWorking(working) {
  $("scanBtn").disabled = working;
  $("prepareBtn").disabled = working || !state.images.length;
}

function getConfig() {
  return {
    inputDir: readValue("inputDir"),
    outputDir: readValue("outputDir"),
    targetSizes: selectedTargetSizes(),
    cropMargin: readNumber("cropMargin", 0),
    trimThreshold: readNumber("trimThreshold", 18),
    allowRotate: readChecked("allowRotate", true),
    padCropX: readNumber("padCropX", 0.5),
    neckRatio: readNumber("neckRatio", 0.14),
    upscalerMode: readValue("upscalerMode", "none"),
    sdWebuiUrl: readValue("sdWebuiUrl", "http://127.0.0.1:7860"),
    sdWebuiUpscaler: readValue("sdWebuiUpscaler", "R-ESRGAN 4x+ Anime6B"),
    realesrganExe: readValue("realesrganExe"),
    realesrganModel: readValue("realesrganModel", "realesrgan-x4plus-anime"),
    realesrganModelDir: readValue("realesrganModelDir"),
    realesrganScale: readValue("realesrganScale", "1"),
    realesrganTile: readValue("realesrganTile"),
    upscalerCommand: readValue("upscalerCommand"),
  };
}

async function postJson(url, payload = {}) {
  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    throw new Error(`通信できませんでした: ${error.message}`);
  }

  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`サーバー応答を読めませんでした: ${response.status}`);
  }
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `request failed: ${response.status}`);
  }
  return data;
}

// サムネは320px正方形キャンバスに中央配置されているので、
// 元画像のy座標 <-> サムネ上の位置(0..1) を相互変換する
function thumbGeometry(image) {
  const size = image.size || null;
  if (!size || !size[0] || !size[1]) return null;
  const [w, h] = size;
  const scale = 320 / Math.max(w, h);
  const imgFracH = (h * scale) / 320;
  return { h, topFrac: (1 - imgFracH) / 2, imgFracH };
}

function defaultNeckY(image) {
  const size = image.size || [0, 0];
  const cb = image.contentBox || [0, 0, size[0], size[1]];
  return cb[1] + readNumber("neckRatio", 0.14) * Math.max(1, cb[3] - cb[1]);
}

function neckYOf(image) {
  return state.neckY[image.id] != null ? state.neckY[image.id] : defaultNeckY(image);
}

function neckLineFrac(image) {
  const geo = thumbGeometry(image);
  if (!geo) return 0.2;
  const y = Math.min(geo.h, Math.max(0, neckYOf(image)));
  return geo.topFrac + (y / geo.h) * geo.imgFracH;
}

function fracToNeckY(image, frac) {
  const geo = thumbGeometry(image);
  if (!geo) return null;
  const y = ((frac - geo.topFrac) / geo.imgFracH) * geo.h;
  return Math.min(geo.h, Math.max(0, Math.round(y)));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderImages() {
  const grid = $("imageGrid");
  if (!state.images.length) {
    grid.className = "image-grid empty";
    grid.innerHTML = '<div class="empty-state">フォルダを指定して「画像一覧表示」を押してください。</div>';
    $("imageCount").textContent = "画像未読み込み";
    return;
  }

  grid.className = "image-grid";
  $("imageCount").textContent = `${state.images.length}枚の画像`;
  grid.innerHTML = state.images
    .map((image) => {
      const mode = state.modes[image.id] || image.mode || "normal";
      const results = image.results || [];
      const status = image.prepared
        ? `<div class="tag-source">整形済み (${results.length}枚)</div>`
        : '<div class="tag-source pending">未整形</div>';
      const warning = (image.warnings || []).length
        ? `<div class="unknown">警告: ${escapeHtml(image.warnings.join(" / "))}</div>`
        : "";
      const resultGrid = results.length
        ? `<div class="result-grid">${results
            .map((r) => {
              const fullUrl = `/api/output?session=${encodeURIComponent(state.sessionId)}&path=${encodeURIComponent(r.image)}`;
              const label = `${KIND_LABELS[r.kind] || r.kind} ${r.targetSize || ""}`;
              return `
              <figure class="result-thumb" title="クリックで拡大">
                <img src="${r.thumbUrl}" alt="${escapeHtml(r.kind)}" data-full="${escapeHtml(fullUrl)}" data-caption="${escapeHtml(label)}">
                <figcaption>
                  ${escapeHtml(label)}
                  ${r.fallback ? '<span class="badge-fallback" title="' + escapeHtml(r.fallback) + '">自動調整</span>' : ""}
                </figcaption>
              </figure>`;
            })
            .join("")}</div>`
        : "";
      const neckLine =
        mode === "fullbody"
          ? `<div class="neck-line" data-neck-id="${escapeHtml(image.id)}" style="top:${(neckLineFrac(image) * 100).toFixed(2)}%">
               <span class="neck-label">首から下 ここから↓（ドラッグで調整）</span>
             </div>`
          : "";
      return `
        <article class="image-card">
          <div class="thumb-wrap">
            <img src="${image.thumbUrl}" alt="${escapeHtml(image.name)}">
            ${neckLine}
          </div>
          <div class="card-body">
            <div class="file-name">${escapeHtml(image.name)}</div>
            <label class="checkline mode-toggle">
              <input type="checkbox" data-mode-toggle data-id="${escapeHtml(image.id)}" ${mode === "fullbody" ? "checked" : ""}>
              全身絵として処理（4枚生成）
            </label>
            ${status}
            ${warning}
            ${resultGrid}
          </div>
        </article>
      `;
    })
    .join("");
}

async function scanImages() {
  setStatus("scanning");
  setWorking(true);
  setProgress("画像一覧を読み込み中", 0, true);
  try {
    const data = await postJson("/api/prepare/scan", getConfig());
    state.sessionId = data.sessionId;
    state.images = data.images || [];
    state.outputDir = data.outputDir || "";
    renderImages();
    $("outputSummary").textContent = state.outputDir ? `出力先: ${state.outputDir}` : "未実行";
    setProgress(`${state.images.length}枚を読み込みました`, 100);
    setStatus("ready");
  } catch (error) {
    setProgress("エラー", 0);
    setStatus("error");
    alert(error.message);
  } finally {
    setWorking(false);
  }
}

async function prepareImages() {
  if (!state.sessionId || !state.images.length) {
    alert("先に画像一覧表示を押してください。");
    return;
  }
  setStatus("preparing");
  setWorking(true);
  try {
    const total = state.images.length;
    const config = getConfig();
    for (let index = 0; index < total; index += 1) {
      const image = state.images[index];
      const percent = Math.round((index / total) * 100);
      setProgress(`画像整形中 ${index + 1}/${total}: ${image.name}`, percent);
      const mode = state.modes[image.id] || "normal";
      const data = await postJson("/api/prepare/image", {
        ...config,
        sessionId: state.sessionId,
        imageId: image.id,
        mode,
        neckY: mode === "fullbody" ? Math.round(neckYOf(image)) : null,
      });
      state.images[index] = data.image;
      state.outputDir = data.outputDir || state.outputDir;
      $("outputSummary").textContent = `出力先: ${data.datasetDir || state.outputDir}`;
      renderImages();
    }
    setProgress(`画像整形完了: ${total}枚`, 100);
    setStatus("done");
  } catch (error) {
    setProgress("エラー", 0);
    setStatus("error");
    alert(error.message);
  } finally {
    setWorking(false);
  }
}

async function pickFolder(targetId) {
  try {
    const data = await postJson("/api/pick-folder", { initial: readValue(targetId) });
    if (data.path) {
      $(targetId).value = data.path;
    }
  } catch (error) {
    alert(error.message);
  }
}

function openLightbox(src, caption) {
  $("lightboxImg").src = src;
  $("lightboxCaption").textContent = caption || "";
  $("lightbox").hidden = false;
}

function closeLightbox() {
  $("lightbox").hidden = true;
  $("lightboxImg").src = "";
}

function renderUpscalerBlocks() {
  const mode = readValue("upscalerMode", "none");
  document.querySelectorAll("[data-upscaler-block]").forEach((block) => {
    block.hidden = block.dataset.upscalerBlock !== mode;
  });
}

function wireEvents() {
  $("scanBtn").addEventListener("click", scanImages);
  $("prepareBtn").addEventListener("click", prepareImages);
  $("upscalerMode").addEventListener("change", renderUpscalerBlocks);
  document.querySelectorAll(".target-size-choice").forEach((input) => {
    input.addEventListener("change", selectedTargetSizes);
  });
  $("padCropX").addEventListener("input", () => {
    $("padCropXValue").textContent = Number(readValue("padCropX", "0.5")).toFixed(2);
  });
  $("imageGrid").addEventListener("change", (event) => {
    const target = event.target;
    if (target.matches("[data-mode-toggle]")) {
      state.modes[target.dataset.id] = target.checked ? "fullbody" : "normal";
      renderImages(); // 首ラインの表示/非表示を反映
    }
  });
  // 首ラインのドラッグ
  $("imageGrid").addEventListener("pointerdown", (event) => {
    const line = event.target.closest(".neck-line");
    if (!line) return;
    event.preventDefault();
    const image = state.images.find((item) => item.id === line.dataset.neckId);
    if (!image) return;
    const wrap = line.parentElement;
    const onMove = (moveEvent) => {
      const rect = wrap.getBoundingClientRect();
      const frac = Math.min(1, Math.max(0, (moveEvent.clientY - rect.top) / rect.height));
      const y = fracToNeckY(image, frac);
      if (y == null) return;
      state.neckY[image.id] = y;
      line.style.top = `${(neckLineFrac(image) * 100).toFixed(2)}%`;
    };
    const onUp = () => {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
    };
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
  });
  $("browseInput").addEventListener("click", () => pickFolder("inputDir"));
  $("browseOutput").addEventListener("click", () => pickFolder("outputDir"));
  $("imageGrid").addEventListener("click", (event) => {
    const img = event.target.closest(".result-thumb img");
    if (img && img.dataset.full) {
      openLightbox(img.dataset.full, img.dataset.caption);
    }
  });
  $("lightbox").addEventListener("click", closeLightbox);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeLightbox();
  });
}

wireEvents();
selectedTargetSizes();
renderUpscalerBlocks();

const state = {
  sessionId: null,
  images: [],
  outputDir: "",
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
      const result = image.result || {};
      const status = image.prepared
        ? `<div class="tag-source">整形済み: ${escapeHtml(result.targetSize || "")}</div>`
        : '<div class="tag-source pending">未整形</div>';
      const warning = (image.warnings || []).length
        ? `<div class="unknown">警告: ${escapeHtml(image.warnings.join(" / "))}</div>`
        : "";
      return `
        <article class="image-card">
          <div class="thumb-wrap">
            <img src="${image.thumbUrl}" alt="${escapeHtml(image.name)}">
          </div>
          <div class="card-body">
            <div class="file-name">${escapeHtml(image.name)}</div>
            ${status}
            ${warning}
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
      const data = await postJson("/api/prepare/image", {
        ...config,
        sessionId: state.sessionId,
        imageId: image.id,
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
}

wireEvents();
selectedTargetSizes();
renderUpscalerBlocks();

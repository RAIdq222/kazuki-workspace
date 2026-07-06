const state = {
  sessionId: null,
  images: [],
  dictionary: null,
  triggerDefinitions: [],
  assignments: {},
};

const $ = (id) => document.getElementById(id);

function setStatus(text) {
  $("serverStatus").textContent = text;
}

function readValue(id, fallback = "") {
  const element = $(id);
  return element ? element.value.trim() : fallback;
}

function readNumber(id, fallback) {
  const value = readValue(id, String(fallback));
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function readChecked(id, fallback = false) {
  const element = $(id);
  return element ? element.checked : fallback;
}

function writeValue(id, value) {
  const element = $(id);
  if (element) element.value = value;
}

function writeChecked(id, value) {
  const element = $(id);
  if (element) element.checked = Boolean(value);
}

function setProgress(text, value = 0, indeterminate = false) {
  const bar = $("taskProgress");
  const label = $("progressText");
  if (!bar || !label) return;
  if (indeterminate) {
    bar.removeAttribute("value");
  } else {
    bar.value = Math.max(0, Math.min(100, value));
  }
  label.textContent = text;
}

function setWorking(working) {
  ["scanBtn", "tagBtn", "buildBtn"].forEach((id) => {
    const button = $(id);
    if (button) button.disabled = working || (id !== "scanBtn" && !state.images.length);
  });
}

function getConfig() {
  return {
    inputDir: readValue("inputDir"),
    outputDir: readValue("outputDir"),
    characterTrigger: readValue("characterTrigger"),
    commonTags: readValue("commonTags"),
    targetSizes: readValue("targetSizes"),
    cropMargin: readNumber("cropMargin", 0.08),
    trimThreshold: readNumber("trimThreshold", 18),
    allowRotate: readChecked("allowRotate", true),
    autoVocabularyRefresh: false,
    eva2Model: readValue("eva2Model", "wd-eva02-large-tagger-v3") || "wd-eva02-large-tagger-v3",
    eva2Threshold: readNumber("eva2Threshold", 0.35),
    useSidecarFallback: readChecked("useSidecarFallback", true),
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

function parseTags(text) {
  const seen = new Set();
  const result = [];
  text
    .replace(/\n/g, ",")
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean)
    .forEach((tag) => {
      if (!seen.has(tag)) {
        seen.add(tag);
        result.push(tag);
      }
    });
  return result;
}

function joinTags(tags) {
  const seen = new Set();
  return tags
    .map((tag) => tag.trim())
    .filter(Boolean)
    .filter((tag) => {
      if (seen.has(tag)) return false;
      seen.add(tag);
      return true;
    })
    .join(", ");
}

function captionFor(image) {
  const config = getConfig();
  const selected = state.assignments[image.id] || [];
  const triggerTokens = selected
    .map((triggerId) => state.triggerDefinitions.find((item) => item.id === triggerId)?.token || "")
    .filter(Boolean);
  return joinTags([
    config.characterTrigger,
    ...parseTags(config.commonTags),
    ...triggerTokens,
    ...(image.keptTags || []),
  ]);
}

function renderSummary(dictionary) {
  if (!dictionary || !dictionary.ok) {
    $("summary").textContent = dictionary?.message || "未設定です。詳細設定で参照LoRA置き場を指定してください。";
    return;
  }
  if (!dictionary.tagCount) {
    $("summary").textContent = dictionary.message || "タグ語彙は空です。候補タグは削れません。";
    return;
  }
  const total = dictionary.totalTagCount && dictionary.totalTagCount !== dictionary.tagCount
    ? ` / 全${dictionary.totalTagCount}語`
    : "";
  const duplicate = dictionary.duplicateUses ? ` / 重複${dictionary.duplicateUses}件を統合` : "";
  const roots = dictionary.rootCount ? ` / ${dictionary.rootCount}か所` : "";
  const min = dictionary.minCount && dictionary.minCount > 1 ? ` / ${dictionary.minCount}回以上` : "";
  $("summary").textContent =
    `使用中 ${dictionary.tagCount}語${total}${roots}${min}${duplicate}` +
    (dictionary.created ? ` / 更新 ${dictionary.created}` : "");
}

function renderTaggerStatus(tagger) {
  const target = $("taggerStatus");
  const downloadButton = $("downloadTaggerBtn");
  if (!target) return;
  if (!tagger) {
    target.textContent = "未確認";
    return;
  }
  if (tagger.ready) {
    const onnxSize = tagger.files?.onnx?.size || 0;
    const sizeText = onnxSize ? ` / ${Math.round(onnxSize / 1024 / 1024)}MB` : "";
    target.textContent = `保存済み: ${tagger.model}${sizeText}`;
    if (downloadButton) downloadButton.disabled = true;
    return;
  }
  target.textContent = `未保存: ${tagger.model}。初回ダウンロードが必要です。`;
  if (downloadButton) downloadButton.disabled = false;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function addTrigger(label = "", token = "") {
  const id = `trg_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  state.triggerDefinitions.push({ id, label, token });
  renderTriggers();
  renderImages();
}

function renderTriggers() {
  const rows = $("triggerRows");
  rows.innerHTML = state.triggerDefinitions
    .map(
      (item) => `
        <div class="trigger-row" data-trigger-id="${item.id}">
          <label>条件名<input class="trigger-label" type="text" value="${escapeHtml(item.label)}" placeholder="例: ジャケットあり"></label>
          <label>入れるタグ<input class="trigger-token" type="text" value="${escapeHtml(item.token)}" placeholder="例: SJKT01"></label>
          <button class="remove-trigger" type="button" title="削除">×</button>
        </div>
      `,
    )
    .join("");

  rows.querySelectorAll(".trigger-row").forEach((row) => {
    const id = row.dataset.triggerId;
    row.querySelector(".trigger-label").addEventListener("input", (event) => {
      const item = state.triggerDefinitions.find((trigger) => trigger.id === id);
      item.label = event.target.value;
      renderBulkOptions();
      renderImages();
    });
    row.querySelector(".trigger-token").addEventListener("input", (event) => {
      const item = state.triggerDefinitions.find((trigger) => trigger.id === id);
      item.token = event.target.value;
      renderBulkOptions();
      updateCaptionsOnly();
    });
    row.querySelector(".remove-trigger").addEventListener("click", () => {
      state.triggerDefinitions = state.triggerDefinitions.filter((trigger) => trigger.id !== id);
      Object.keys(state.assignments).forEach((imageId) => {
        state.assignments[imageId] = (state.assignments[imageId] || []).filter((triggerId) => triggerId !== id);
      });
      renderTriggers();
      renderImages();
    });
  });
  renderBulkOptions();
}

function renderBulkOptions() {
  $("bulkTrigger").innerHTML = state.triggerDefinitions
    .map((item) => `<option value="${item.id}">${escapeHtml(item.label || item.token || "未設定")}</option>`)
    .join("");
}

function renderImages() {
  const grid = $("imageGrid");
  if (!state.images.length) {
    grid.className = "image-grid empty";
    grid.innerHTML = '<div class="empty-state">フォルダを指定して「サムネ一覧表示」を押してください。</div>';
    $("imageCount").textContent = "画像未読み込み";
    return;
  }

  grid.className = "image-grid";
  $("imageCount").textContent = `${state.images.length}枚の画像`;
  grid.innerHTML = state.images.map(renderImageCard).join("");

  grid.querySelectorAll(".image-card").forEach((card) => {
    const imageId = card.dataset.imageId;
    card.querySelector(".select-box").addEventListener("change", (event) => {
      card.classList.toggle("selected", event.target.checked);
    });
    card.querySelectorAll(".trigger-toggle").forEach((box) => {
      box.addEventListener("change", (event) => {
        const triggerId = event.target.dataset.triggerId;
        const current = new Set(state.assignments[imageId] || []);
        if (event.target.checked) {
          current.add(triggerId);
        } else {
          current.delete(triggerId);
        }
        state.assignments[imageId] = Array.from(current);
        updateCaption(imageId);
      });
    });
  });
  updateCaptionsOnly();
}

function renderImageCard(image) {
  const selected = new Set(state.assignments[image.id] || []);
  const tagged = Boolean(image.tagged);
  const checks = state.triggerDefinitions
    .map((trigger) => {
      const label = escapeHtml(trigger.label || trigger.token || "未設定");
      return `
        <label>
          <input class="trigger-toggle" type="checkbox" data-trigger-id="${trigger.id}" ${selected.has(trigger.id) ? "checked" : ""}>
          ${label}
        </label>
      `;
    })
    .join("");
  const unknown = (image.unknownTags || []).slice(0, 10);
  const unknownText = unknown.length
    ? `<div class="unknown">語彙外: ${escapeHtml(unknown.join(", "))}${image.unknownTags.length > 10 ? " ..." : ""}</div>`
    : "";
  const warnings = (image.warnings || []).slice(0, 3);
  const warningsText = warnings.length
    ? `<div class="unknown">警告: ${escapeHtml(warnings.join(" / "))}</div>`
    : "";
  const tagInfo = image.tagSource && image.tagSource !== "none"
    ? `<div class="tag-source">${escapeHtml(image.tagSource)}: ${image.rawTags?.length || 0}件 → 採用${image.keptTags?.length || 0}件</div>`
    : "";
  return `
    <article class="image-card" data-image-id="${image.id}">
      <div class="thumb-wrap">
        <img src="${image.thumbUrl}" alt="${escapeHtml(image.name)}">
        <input class="select-box" type="checkbox" aria-label="選択">
      </div>
      <div class="card-body">
        <div class="file-name">${escapeHtml(image.name)}</div>
        ${
          tagged
            ? `
              <div class="trigger-checks">${checks || '<span class="hint">管理トリガーなし</span>'}</div>
              ${tagInfo}
              <div class="caption-preview" data-caption-for="${image.id}"></div>
              ${unknownText}
              ${warningsText}
            `
            : '<div class="tag-source pending">未タグ付け</div>'
        }
      </div>
    </article>
  `;
}

function updateCaption(imageId) {
  const image = state.images.find((item) => item.id === imageId);
  const target = document.querySelector(`[data-caption-for="${imageId}"]`);
  if (image && target) {
    target.textContent = captionFor(image) || "(空のキャプション)";
  }
}

function updateCaptionsOnly() {
  state.images.forEach((image) => updateCaption(image.id));
}

function selectedImageIds() {
  return Array.from(document.querySelectorAll(".image-card"))
    .filter((card) => card.querySelector(".select-box").checked)
    .map((card) => card.dataset.imageId);
}

function applyBulk(triggerId, enabled) {
  if (!triggerId) return;
  selectedImageIds().forEach((imageId) => {
    const current = new Set(state.assignments[imageId] || []);
    if (enabled) {
      current.add(triggerId);
    } else {
      current.delete(triggerId);
    }
    state.assignments[imageId] = Array.from(current);
  });
  renderImages();
}

function applySettings(settings) {
  if (!settings) return;
  if (settings.targetSizes) writeValue("targetSizes", Array.isArray(settings.targetSizes)
    ? settings.targetSizes.join(", ")
    : settings.targetSizes);
  if (settings.cropMargin !== undefined) writeValue("cropMargin", settings.cropMargin);
  if (settings.trimThreshold !== undefined) writeValue("trimThreshold", settings.trimThreshold);
  if (settings.allowRotate !== undefined) writeChecked("allowRotate", settings.allowRotate);
  writeValue("eva2Model", settings.eva2Model || "wd-eva02-large-tagger-v3");
  if (settings.eva2Threshold !== undefined) writeValue("eva2Threshold", settings.eva2Threshold);
  if (settings.useSidecarFallback !== undefined) writeChecked("useSidecarFallback", settings.useSidecarFallback);
  if (settings.upscalerMode) writeValue("upscalerMode", settings.upscalerMode);
  if (settings.sdWebuiUrl) writeValue("sdWebuiUrl", settings.sdWebuiUrl);
  if (settings.sdWebuiUpscaler) writeValue("sdWebuiUpscaler", settings.sdWebuiUpscaler);
  if (settings.realesrganExe !== undefined) writeValue("realesrganExe", settings.realesrganExe);
  if (settings.realesrganModel) writeValue("realesrganModel", settings.realesrganModel);
  if (settings.realesrganModelDir !== undefined) writeValue("realesrganModelDir", settings.realesrganModelDir);
  if (settings.realesrganScale !== undefined) writeValue("realesrganScale", settings.realesrganScale);
  if (settings.realesrganTile !== undefined) writeValue("realesrganTile", settings.realesrganTile);
  if (settings.upscalerCommand !== undefined) writeValue("upscalerCommand", settings.upscalerCommand);
  renderUpscalerBlocks();
}

async function loadSettings() {
  setStatus("loading");
  setProgress("設定を確認中", 0, true);
  try {
    const data = await postJson("/api/settings");
    applySettings(data.settings);
    state.dictionary = data.dictionary;
    renderSummary(data.dictionary);
    renderTaggerStatus(data.tagger);
    setStatus("ready");
    setProgress("待機中", 0);
  } catch (error) {
    setStatus("error");
    setProgress("エラー", 0);
    alert(error.message);
  }
}

async function downloadTaggerModel() {
  setStatus("downloading model");
  const button = $("downloadTaggerBtn");
  if (button) button.disabled = true;
  try {
    const data = await postJson("/api/tagger/download", getConfig());
    applySettings(data.settings);
    renderTaggerStatus(data.tagger);
    setStatus("ready");
  } catch (error) {
    if (button) button.disabled = false;
    setStatus("error");
    alert(error.message);
  }
}

async function refreshVocabulary() {
  setStatus("updating vocabulary");
  setProgress("辞書を更新中", 0, true);
  try {
    const data = await postJson("/api/vocabulary/refresh", getConfig());
    applySettings(data.settings);
    state.dictionary = data.dictionary;
    renderSummary(data.dictionary);
    setStatus("ready");
    setProgress("辞書更新完了", 100);
  } catch (error) {
    setStatus("error");
    setProgress("エラー", 0);
    alert(error.message);
  }
}

async function scanImages() {
  setStatus("scanning");
  setWorking(true);
  setProgress("サムネ一覧を読み込み中", 0, true);
  try {
    const config = getConfig();
    const data = await postJson("/api/scan", config);
    state.sessionId = data.sessionId;
    state.images = data.images || [];
    state.dictionary = data.dictionary;
    state.assignments = {};
    applySettings(data.settings);
    renderSummary(data.dictionary);
    renderTaggerStatus(data.tagger);
    renderImages();
    $("tagBtn").disabled = state.images.length === 0;
    $("buildBtn").disabled = state.images.length === 0;
    setStatus("ready");
    setProgress(`${state.images.length}枚を読み込みました`, 100);
  } catch (error) {
    setStatus("error");
    setProgress("エラー", 0);
    alert(error.message);
  } finally {
    setWorking(false);
  }
}

async function tagImages() {
  if (!state.sessionId || !state.images.length) {
    alert("先にサムネ一覧表示を押してください。");
    return;
  }
  setStatus("tagging");
  setWorking(true);
  try {
    const config = getConfig();
    setProgress("辞書とEVA02を準備中", 0, true);
    const prepared = await postJson("/api/tag/prepare", {
      ...config,
      sessionId: state.sessionId,
    });
    applySettings(prepared.settings);
    state.dictionary = prepared.dictionary;
    renderSummary(prepared.dictionary);
    renderTaggerStatus(prepared.tagger);

    const total = state.images.length;
    for (let index = 0; index < total; index += 1) {
      const image = state.images[index];
      const percent = Math.round((index / total) * 100);
      setProgress(`タグつけ中 ${index + 1}/${total}: ${image.name}`, percent);
      const data = await postJson("/api/tag/image", {
        sessionId: state.sessionId,
        imageId: image.id,
      });
      state.images[index] = data.image;
      renderImages();
    }
    setStatus("ready");
    setProgress(`タグつけ完了: ${total}枚`, 100);
  } catch (error) {
    setStatus("error");
    setProgress("エラー", 0);
    alert(error.message);
  } finally {
    setWorking(false);
  }
}

async function buildPreflight() {
  setStatus("building");
  setWorking(true);
  setProgress("AI Toolkit投入前データを作成中", 0, true);
  try {
    const config = getConfig();
    const data = await postJson("/api/build", {
      ...config,
      sessionId: state.sessionId,
      triggerDefinitions: state.triggerDefinitions,
      assignments: state.assignments,
    });
    $("resultText").textContent = `${data.count}枚を出力しました。\n${data.datasetDir}`;
    $("warningText").textContent = (data.warnings || []).join("\n");
    $("resultDialog").showModal();
    setStatus("done");
    setProgress(`${data.count}枚を出力しました`, 100);
  } catch (error) {
    setStatus("error");
    setProgress("エラー", 0);
    alert(error.message);
  } finally {
    setWorking(false);
  }
}

function wireEvents() {
  if ($("vocabularyRefreshBtn")) $("vocabularyRefreshBtn").addEventListener("click", refreshVocabulary);
  if ($("downloadTaggerBtn")) $("downloadTaggerBtn").addEventListener("click", downloadTaggerModel);
  $("scanBtn").addEventListener("click", scanImages);
  $("tagBtn").addEventListener("click", tagImages);
  $("buildBtn").addEventListener("click", buildPreflight);
  $("startBtn").addEventListener("click", () => {
    $("resultText").textContent = "このボタンはプレースホルダーです。AI Toolkit投入と学習開始は次フェーズで実装します。";
    $("warningText").textContent = "";
    $("resultDialog").showModal();
  });
  $("closeDialogBtn").addEventListener("click", () => $("resultDialog").close());
  $("addTriggerBtn").addEventListener("click", () => addTrigger());
  $("selectAllBtn").addEventListener("click", () => {
    document.querySelectorAll(".image-card").forEach((card) => {
      card.querySelector(".select-box").checked = true;
      card.classList.add("selected");
    });
  });
  $("clearSelectionBtn").addEventListener("click", () => {
    document.querySelectorAll(".image-card").forEach((card) => {
      card.querySelector(".select-box").checked = false;
      card.classList.remove("selected");
    });
  });
  $("bulkOnBtn").addEventListener("click", () => applyBulk($("bulkTrigger").value, true));
  $("bulkOffBtn").addEventListener("click", () => applyBulk($("bulkTrigger").value, false));
  if ($("upscalerMode")) $("upscalerMode").addEventListener("change", renderUpscalerBlocks);
  ["characterTrigger", "commonTags"].forEach((id) => $(id).addEventListener("input", updateCaptionsOnly));
}

function renderUpscalerBlocks() {
  const mode = readValue("upscalerMode", "none");
  document.querySelectorAll("[data-upscaler-block]").forEach((block) => {
    block.hidden = block.dataset.upscalerBlock !== mode;
  });
}

// フォルダ欄はブラウザに保存して、ページを開き直しても消えないようにする
// （キーは整形画面と別: タグ付けの入力は「整形済み」フォルダを指すことが多いため）
["inputDir", "outputDir"].forEach((id) => {
  const element = $(id);
  if (!element) return;
  const key = `preflight:tagging:${id}`;
  const saved = localStorage.getItem(key);
  if (saved && !element.value) {
    element.value = saved;
  }
  ["input", "change"].forEach((type) =>
    element.addEventListener(type, () => localStorage.setItem(key, element.value.trim()))
  );
});

wireEvents();
addTrigger("ジャケットあり", "SJKT01");
addTrigger("マスクあり", "SMSK01");
renderUpscalerBlocks();
loadSettings();

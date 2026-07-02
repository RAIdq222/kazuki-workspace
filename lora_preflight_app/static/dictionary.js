const $ = (id) => document.getElementById(id);

function setStatus(text) {
  $("serverStatus").textContent = text;
}

async function postJson(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || data.message || `request failed: ${response.status}`);
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

function parseTags(text) {
  const seen = new Set();
  const tags = [];
  text
    .replace(/\n/g, ",")
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean)
    .forEach((tag) => {
      if (!seen.has(tag)) {
        seen.add(tag);
        tags.push(tag);
      }
    });
  return tags;
}

function dictionaryToText(dictionary) {
  const order = dictionary.order && dictionary.order.length
    ? dictionary.order
    : (dictionary.tags || []).map((item) => item.tag);
  return order.join("\n");
}

function renderDictionary(dictionary) {
  const count = dictionary.tagCount || 0;
  const total = dictionary.totalTagCount && dictionary.totalTagCount !== count
    ? ` / 全${dictionary.totalTagCount}語`
    : "";
  const source = dictionary.source ? ` / ${dictionary.source}` : "";
  const updated = dictionary.created ? ` / 更新 ${dictionary.created}` : "";
  $("dictionarySummary").textContent = count
    ? `使用中 ${count}語${total}${source}${updated}`
    : (dictionary.message || "辞書未作成");

  const tags = (dictionary.tags || []).slice(0, 120);
  $("dictionaryTags").innerHTML = tags
    .map((item) => `<span class="tag">${escapeHtml(item.tag)} ${item.count || ""}</span>`)
    .join("");
  $("manualTags").value = dictionaryToText(dictionary);
}

async function loadDictionary() {
  setStatus("loading");
  try {
    const dictionary = await postJson("/api/dictionary");
    renderDictionary(dictionary);
    setStatus("ready");
  } catch (error) {
    setStatus("error");
    alert(error.message);
  }
}

async function saveManualDictionary() {
  const tags = parseTags($("manualTags").value);
  if (!tags.length) {
    alert("保存するタグが空です。辞書を空に戻す場合は「空に戻す」を押してください。");
    return;
  }
  setStatus("saving");
  try {
    const dictionary = await postJson("/api/dictionary", { tagsText: tags.join(", ") });
    renderDictionary(dictionary);
    setStatus("saved");
  } catch (error) {
    setStatus("error");
    alert(error.message);
  }
}

async function clearDictionary() {
  if (!confirm("タグ語彙フィルターを空に戻します。よろしいですか？")) return;
  setStatus("clearing");
  try {
    const dictionary = await postJson("/api/dictionary", { clear: true });
    renderDictionary(dictionary);
    setStatus("ready");
  } catch (error) {
    setStatus("error");
    alert(error.message);
  }
}

async function buildDictionary() {
  const roots = $("vocabularyRoots").value.trim();
  if (!roots) {
    alert("参照LoRA置き場を入力してください。");
    return;
  }
  setStatus("building");
  try {
    const dictionary = await postJson("/api/dictionary/build", {
      vocabularyRoots: roots,
      vocabularyMinCount: Number($("vocabularyMinCount").value || "1"),
    });
    renderDictionary(dictionary);
    setStatus("saved");
  } catch (error) {
    setStatus("error");
    alert(error.message);
  }
}

function wireEvents() {
  $("loadDictionaryBtn").addEventListener("click", loadDictionary);
  $("saveManualBtn").addEventListener("click", saveManualDictionary);
  $("clearDictionaryBtn").addEventListener("click", clearDictionary);
  $("buildDictionaryBtn").addEventListener("click", buildDictionary);
}

wireEvents();
loadDictionary();

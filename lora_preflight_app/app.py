from __future__ import annotations

import hashlib
import argparse
import base64
import csv
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
import webbrowser
from collections import Counter, defaultdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

try:
    from PIL import Image
except ImportError as exc:
    print("Pillow is required. Install it with: pip install -r requirements.txt")
    raise exc

import preflight_core as pfc


APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"
CONFIG_ROOT = APP_ROOT / "config"
SESSION_ROOT = APP_ROOT / ".sessions"
MODEL_ROOT = APP_ROOT / "models"
DICTIONARY_PATH = CONFIG_ROOT / "tag_dictionary.json"
SETTINGS_PATH = CONFIG_ROOT / "default_settings.json"
CONFIG_ROOT.mkdir(exist_ok=True)
SESSION_ROOT.mkdir(exist_ok=True)
MODEL_ROOT.mkdir(exist_ok=True)

SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
DEFAULT_TARGET_SIZES = [(1024, 1024), (1152, 896), (1216, 832), (1344, 768), (1536, 640)]
DEFAULT_SETTINGS = {
    "targetSizes": ["1024x1024", "1152x896", "1216x832", "1344x768", "1536x640"],
    "allowRotate": True,
    "cropMargin": 0.0,
    "trimThreshold": 18,
    "padCropX": 0.5,
    "maxCropFrac": 0.15,
    "fullbodyBaseHeight": 2200,
    "fullbodyTile": 1024,
    "neckRatio": 0.14,
    "vocabularyRoots": [],
    "vocabularyMinCount": 1,
    "autoVocabularyRefresh": True,
    "eva2Model": "wd-eva02-large-tagger-v3",
    "eva2Threshold": 0.35,
    "useSidecarFallback": True,
    "upscalerMode": "none",
    "sdWebuiUrl": "http://127.0.0.1:7860",
    "sdWebuiUpscaler": "R-ESRGAN 4x+ Anime6B",
    "realesrganExe": "",
    "realesrganModel": "realesrgan-x4plus-anime",
    "realesrganModelDir": "",
    "realesrganScale": "1",
    "realesrganTile": "",
    "upscalerCommand": "",
}
SETTING_KEYS = set(DEFAULT_SETTINGS)
UPSCALER_KEYS = (
    "upscalerMode",
    "sdWebuiUrl",
    "sdWebuiUpscaler",
    "realesrganExe",
    "realesrganModel",
    "realesrganModelDir",
    "realesrganScale",
    "realesrganTile",
    "upscalerCommand",
)
SESSIONS: dict[str, dict] = {}
TAGGER_SESSIONS: dict[str, object] = {}
TAGGER_MODEL_REPOS = {
    "wd-eva02-large-tagger-v3": "SmilingWolf/wd-eva02-large-tagger-v3",
}
TAGGER_MODEL_FILES = ("model.onnx", "selected_tags.csv")


def safe_print(*args) -> None:
    try:
        if sys.stdout:
            print(*args)
    except Exception:
        pass


def normalize_tag_name(tag: str) -> str:
    return re.sub(r"\s+", " ", str(tag or "").strip().replace("_", " "))


def parse_tags(text: str) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for raw in text.replace("\n", ",").split(","):
        tag = normalize_tag_name(raw)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


def join_tags(tags: list[str]) -> str:
    clean: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        tag = tag.strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        clean.append(tag)
    return ", ".join(clean)


def parse_target_sizes(value) -> list[tuple[int, int]]:
    if isinstance(value, str):
        tokens = re.split(r"[\s,]+", value.strip())
    elif isinstance(value, list):
        tokens = value
    else:
        tokens = []

    sizes: list[tuple[int, int]] = []
    for token in tokens:
        if isinstance(token, (list, tuple)) and len(token) == 2:
            w, h = int(token[0]), int(token[1])
        else:
            match = re.match(r"^\s*(\d+)\s*[xX*]\s*(\d+)\s*$", str(token))
            if not match:
                continue
            w, h = int(match.group(1)), int(match.group(2))
        if w > 0 and h > 0 and (w, h) not in sizes:
            sizes.append((w, h))
    return sizes or DEFAULT_TARGET_SIZES


def list_images(folder: Path) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    return sorted(
        [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGES],
        key=lambda p: natural_key(p.name),
    )


def natural_key(text: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def normalize_roots(value) -> list[str]:
    if isinstance(value, str):
        parts = re.split(r"[\r\n;]+", value)
    elif isinstance(value, list):
        parts = value
    else:
        parts = []
    roots: list[str] = []
    seen: set[str] = set()
    for raw in parts:
        root = str(raw).strip().strip('"')
        if not root or root in seen:
            continue
        seen.add(root)
        roots.append(root)
    return roots


def load_settings() -> dict:
    data = {}
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    settings = {**DEFAULT_SETTINGS, **{key: data[key] for key in data if key in SETTING_KEYS}}
    settings["vocabularyRoots"] = normalize_roots(settings.get("vocabularyRoots", []))
    settings["vocabularyMinCount"] = max(1, int(settings.get("vocabularyMinCount", 1) or 1))
    settings["eva2Threshold"] = min(1.0, max(0.01, float(settings.get("eva2Threshold", 0.35) or 0.35)))
    settings["autoVocabularyRefresh"] = bool(settings.get("autoVocabularyRefresh", True))
    settings["useSidecarFallback"] = bool(settings.get("useSidecarFallback", True))
    settings["padCropX"] = min(1.0, max(0.0, float(settings.get("padCropX", 0.5) or 0.0)))
    settings["maxCropFrac"] = min(1.0, max(0.01, float(settings.get("maxCropFrac", 0.15) or 0.15)))
    settings["fullbodyBaseHeight"] = max(256, int(settings.get("fullbodyBaseHeight", 2200) or 2200))
    settings["fullbodyTile"] = max(64, int(settings.get("fullbodyTile", 1024) or 1024))
    settings["neckRatio"] = min(0.5, max(0.01, float(settings.get("neckRatio", 0.14) or 0.14)))
    return settings


def merge_settings(base: dict, updates: dict) -> dict:
    merged = dict(base)
    for key in SETTING_KEYS:
        if key not in updates:
            continue
        if key == "vocabularyRoots":
            merged[key] = normalize_roots(updates[key])
        elif key == "vocabularyMinCount":
            merged[key] = max(1, int(updates[key] or 1))
        elif key == "eva2Threshold":
            merged[key] = min(1.0, max(0.01, float(updates[key] or 0.35)))
        elif key in {"allowRotate", "autoVocabularyRefresh", "useSidecarFallback"}:
            merged[key] = bool(updates[key])
        elif key == "padCropX":
            merged[key] = min(1.0, max(0.0, float(updates[key] if updates[key] is not None else 0.5)))
        elif key == "maxCropFrac":
            merged[key] = min(1.0, max(0.01, float(updates[key] or 0.15)))
        elif key == "fullbodyBaseHeight":
            merged[key] = max(256, int(updates[key] or 2200))
        elif key == "fullbodyTile":
            merged[key] = max(64, int(updates[key] or 1024))
        elif key == "neckRatio":
            merged[key] = min(0.5, max(0.01, float(updates[key] or 0.14)))
        else:
            merged[key] = updates[key]
    return merged


def save_settings(settings: dict) -> dict:
    normalized = merge_settings(DEFAULT_SETTINGS, settings)
    SETTINGS_PATH.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def has_sidecar_image(txt_path: Path) -> bool:
    return any(txt_path.with_suffix(ext).exists() for ext in SUPPORTED_IMAGES)


def analyze_past_captions(root: Path, min_count: int = 1) -> dict:
    return analyze_past_caption_roots([str(root)], min_count=min_count)


def analyze_past_caption_roots(roots, min_count: int = 1) -> dict:
    counter: Counter[str] = Counter()
    positions: defaultdict[str, list[int]] = defaultdict(list)
    txt_count = 0
    pair_count = 0
    folder_count = 0
    folders: set[Path] = set()
    warnings: list[str] = []
    normalized_roots = normalize_roots(roots)
    valid_roots: list[Path] = []

    if not normalized_roots:
        return empty_dictionary("参照LoRA置き場が未設定です。")

    for raw_root in normalized_roots:
        root = Path(raw_root).expanduser()
        if not root.exists() or not root.is_dir():
            warnings.append(f"参照LoRA置き場が見つかりません: {raw_root}")
            continue
        valid_roots.append(root)
        for txt in root.rglob("*.txt"):
            txt_count += 1
            if not has_sidecar_image(txt):
                continue
            pair_count += 1
            folders.add(txt.parent)
            try:
                tags = parse_tags(txt.read_text(encoding="utf-8-sig", errors="ignore"))
            except OSError as exc:
                warnings.append(f"{txt}: {exc}")
                continue
            for index, tag in enumerate(tags):
                counter[tag] += 1
                positions[tag].append(index)

    if not valid_roots:
        return {
            "ok": False,
            "error": "valid vocabulary root was not found",
            "message": "参照LoRA置き場が見つかりません。",
            "source": "",
            "created": "",
            "tagCount": 0,
            "pairCount": 0,
            "txtCount": 0,
            "folderCount": 0,
            "tags": [],
            "order": [],
            "warnings": warnings,
        }

    folder_count = len(folders)
    min_count = max(1, int(min_count or 1))
    included = {tag for tag, count in counter.items() if count >= min_count}
    order = sorted(
        included,
        key=lambda tag: (
            sum(positions[tag]) / max(len(positions[tag]), 1),
            -counter[tag],
            tag,
        ),
    )
    tags = [
        {
            "tag": tag,
            "count": counter[tag],
            "avgPosition": round(sum(positions[tag]) / max(len(positions[tag]), 1), 2),
        }
        for tag in sorted(included, key=lambda t: (-counter[t], t))
    ]
    return {
        "ok": True,
        "source": "; ".join(str(root) for root in valid_roots),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tagCount": len(tags),
        "totalTagCount": len(counter),
        "pairCount": pair_count,
        "txtCount": txt_count,
        "folderCount": folder_count,
        "rootCount": len(valid_roots),
        "minCount": min_count,
        "duplicateUses": max(0, sum(counter.values()) - len(counter)),
        "tags": tags,
        "order": order,
        "warnings": warnings,
    }


def empty_dictionary(message: str = "辞書未作成") -> dict:
    return {
        "ok": True,
        "source": "",
        "created": "",
        "message": message,
        "tagCount": 0,
        "pairCount": 0,
        "txtCount": 0,
        "folderCount": 0,
        "tags": [],
        "order": [],
    }


def normalize_dictionary(data: dict) -> dict:
    tags = data.get("tags", [])
    if tags and isinstance(tags[0], str):
        tags = [{"tag": tag, "count": 1, "avgPosition": index} for index, tag in enumerate(tags)]
    merged: dict[str, dict] = {}
    for index, item in enumerate(tags):
        tag = normalize_tag_name(item.get("tag", ""))
        if not tag:
            continue
        count = int(item.get("count", 1) or 1)
        avg_position = float(item.get("avgPosition", index) or index)
        if tag in merged:
            merged[tag]["count"] += count
            merged[tag]["avgPosition"] = min(merged[tag]["avgPosition"], avg_position)
        else:
            merged[tag] = {"tag": tag, "count": count, "avgPosition": avg_position}
    tags = list(merged.values())
    order = data.get("order") or [item.get("tag", "") for item in tags]
    order = dedupe([normalize_tag_name(tag) for tag in order if normalize_tag_name(tag)])
    if not order:
        order = [item["tag"] for item in tags]
    return {
        "ok": bool(data.get("ok", True)),
        "source": data.get("source", ""),
        "created": data.get("created", ""),
        "message": data.get("message", ""),
        "tagCount": len({item["tag"] for item in tags}),
        "totalTagCount": int(data.get("totalTagCount", len({item["tag"] for item in tags})) or 0),
        "pairCount": int(data.get("pairCount", 0) or 0),
        "txtCount": int(data.get("txtCount", 0) or 0),
        "folderCount": int(data.get("folderCount", 0) or 0),
        "rootCount": int(data.get("rootCount", 0) or 0),
        "minCount": int(data.get("minCount", 1) or 1),
        "duplicateUses": int(data.get("duplicateUses", 0) or 0),
        "warnings": data.get("warnings", []),
        "tags": tags,
        "order": order,
    }


def load_dictionary() -> dict:
    if not DICTIONARY_PATH.exists():
        return empty_dictionary()
    try:
        return normalize_dictionary(json.loads(DICTIONARY_PATH.read_text(encoding="utf-8")))
    except Exception as exc:
        data = empty_dictionary(f"辞書読み込み失敗: {exc}")
        data["ok"] = False
        return data


def save_dictionary(data: dict) -> dict:
    normalized = normalize_dictionary(data)
    DICTIONARY_PATH.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def refresh_dictionary_from_settings(settings: dict) -> dict:
    roots = normalize_roots(settings.get("vocabularyRoots", []))
    if not roots:
        return load_dictionary()
    data = analyze_past_caption_roots(roots, min_count=settings.get("vocabularyMinCount", 1))
    if data.get("ok"):
        return save_dictionary(data)
    saved = load_dictionary()
    saved["ok"] = False
    saved["message"] = data.get("message") or data.get("error") or "タグ語彙フィルターを更新できませんでした。"
    saved["warnings"] = data.get("warnings", [])
    return saved


def command_with_placeholders(template: str, values: dict[str, str]) -> str:
    command = template
    for key, value in values.items():
        command = command.replace("{" + key + "}", value)
    return command


def parse_tagger_output(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return parse_tags(text)

    def collect(value) -> list[str]:
        if isinstance(value, str):
            return parse_tags(value)
        if isinstance(value, list):
            tags: list[str] = []
            for item in value:
                if isinstance(item, str):
                    tags.extend(parse_tags(item))
                elif isinstance(item, dict):
                    tag = item.get("tag") or item.get("name") or item.get("label")
                    if tag:
                        tags.append(str(tag).strip())
            return tags
        if isinstance(value, dict):
            tags: list[str] = []
            preferred_keys = ("caption", "tag_string", "tags", "general", "character", "rating")
            for key in preferred_keys:
                if key in value:
                    tags.extend(collect(value[key]))
            if tags:
                return tags
            for item in value.values():
                tags.extend(collect(item))
            return tags
        return []

    return dedupe(collect(data))


def tagger_model_dir(model_name: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", model_name or "wd-eva02-large-tagger-v3").strip("._")
    return MODEL_ROOT / safe_name


def tagger_model_paths(model_name: str) -> dict[str, Path]:
    root = tagger_model_dir(model_name)
    return {
        "root": root,
        "onnx": root / "model.onnx",
        "tags": root / "selected_tags.csv",
    }


def tagger_model_status(model_name: str) -> dict:
    paths = tagger_model_paths(model_name)
    files = {}
    ready = True
    for key in ("onnx", "tags"):
        path = paths[key]
        exists = path.exists() and path.is_file() and path.stat().st_size > 0
        ready = ready and exists
        files[key] = {
            "path": str(path),
            "exists": exists,
            "size": path.stat().st_size if exists else 0,
        }
    return {
        "ok": True,
        "model": model_name,
        "ready": ready,
        "root": str(paths["root"]),
        "files": files,
        "needsDownload": not ready,
    }


def download_file(url: str, destination: Path, timeout: int = 1800) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".partial")
    req = Request(url, headers={"User-Agent": "LoRA-Preflight/0.2"})
    with urlopen(req, timeout=timeout) as response, temp_path.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    temp_path.replace(destination)


def download_tagger_model(model_name: str) -> dict:
    repo = TAGGER_MODEL_REPOS.get(model_name)
    if not repo:
        return {"ok": False, "error": f"unknown tagger model: {model_name}"}
    paths = tagger_model_paths(model_name)
    for file_name in TAGGER_MODEL_FILES:
        destination = paths["root"] / file_name
        if destination.exists() and destination.stat().st_size > 0:
            continue
        url = f"https://huggingface.co/{repo}/resolve/main/{file_name}"
        download_file(url, destination)
    TAGGER_SESSIONS.pop(model_name, None)
    return tagger_model_status(model_name)


def load_selected_tags(path: Path) -> list[dict]:
    labels: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = (row.get("name") or row.get("tag") or "").strip()
            if not name:
                continue
            try:
                category = int(row.get("category", "0") or 0)
            except ValueError:
                category = 0
            labels.append({"name": name, "category": category})
    return labels


def make_tagger_input(image_path: Path, size: int):
    import numpy as np

    with Image.open(image_path) as img:
        img = img.convert("RGBA")
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        background.alpha_composite(img)
        img = background.convert("RGB")
        side = max(img.width, img.height)
        canvas = Image.new("RGB", (side, side), (255, 255, 255))
        canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
        canvas = canvas.resize((size, size), Image.Resampling.BICUBIC)
        arr = np.asarray(canvas, dtype=np.float32)
        arr = arr[:, :, ::-1]
        return arr[None, :, :, :]


def get_local_tagger_session(model_name: str):
    cached = TAGGER_SESSIONS.get(model_name)
    if cached:
        return cached

    status = tagger_model_status(model_name)
    if not status["ready"]:
        raise FileNotFoundError("タグモデル未保存です。画面上部の「初回ダウンロード」を押してください。")
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError("onnxruntime がありません。requirements.txt を入れ直してください。") from exc

    paths = tagger_model_paths(model_name)
    session = ort.InferenceSession(str(paths["onnx"]), providers=["CPUExecutionProvider"])
    input_meta = session.get_inputs()[0]
    input_shape = input_meta.shape
    size = 448
    if len(input_shape) >= 3 and isinstance(input_shape[1], int):
        size = int(input_shape[1])
    labels = load_selected_tags(paths["tags"])
    cached = {"session": session, "inputName": input_meta.name, "size": size, "labels": labels}
    TAGGER_SESSIONS[model_name] = cached
    return cached


def run_local_eva2_tagger(
    image_path: Path,
    model_name: str,
    threshold: float,
) -> tuple[list[str], str | None]:
    try:
        tagger = get_local_tagger_session(model_name)
        image_input = make_tagger_input(image_path, tagger["size"])
        outputs = tagger["session"].run(None, {tagger["inputName"]: image_input})
    except Exception as exc:
        return [], str(exc)

    scores = outputs[0]
    try:
        scores = scores[0]
    except Exception:
        pass

    tags: list[str] = []
    for index, label in enumerate(tagger["labels"]):
        if index >= len(scores):
            break
        category = label["category"]
        if category == 9:
            continue
        try:
            score = float(scores[index])
        except Exception:
            continue
        if score >= threshold:
            tags.append(normalize_tag_name(label["name"]))
    if not tags:
        return [], "ローカルEVA2タグgerはタグを返しませんでした。しきい値を下げてください。"
    return dedupe(tags), None


def run_subprocess_upscaler(command: str, temp_path: Path, destination: Path, timeout: int = 900) -> tuple[bool, str | None]:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(APP_ROOT),
        )
    except Exception as exc:
        shutil.copyfile(temp_path, destination)
        return False, f"upscaler command failed: {exc}"

    if result.returncode != 0:
        warning = (result.stderr or result.stdout or "upscaler command failed").strip()[:500]
        shutil.copyfile(temp_path, destination)
        return False, warning

    if not destination.exists():
        shutil.copyfile(temp_path, destination)
        return False, "upscaler command finished but output file was not created."
    return True, None


def run_sd_webui_upscaler(
    temp_path: Path,
    destination: Path,
    webui_url: str,
    upscaler_name: str,
    timeout: int = 900,
) -> tuple[bool, str | None]:
    url = webui_url.rstrip("/") + "/sdapi/v1/extra-single-image"
    image_b64 = base64.b64encode(temp_path.read_bytes()).decode("ascii")
    payload = {
        "resize_mode": 0,
        "show_extras_results": True,
        "gfpgan_visibility": 0,
        "codeformer_visibility": 0,
        "codeformer_weight": 0,
        "upscaling_resize": 1,
        "upscaling_crop": False,
        "upscaler_1": upscaler_name,
        "upscaler_2": "None",
        "extras_upscaler_2_visibility": 0,
        "image": "data:image/png;base64," + image_b64,
    }
    try:
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        shutil.copyfile(temp_path, destination)
        return False, f"SD WebUI upscaler failed: {exc}"

    result_image = data.get("image") or ""
    if "," in result_image:
        result_image = result_image.split(",", 1)[1]
    if not result_image:
        shutil.copyfile(temp_path, destination)
        return False, "SD WebUI upscaler returned no image."

    try:
        destination.write_bytes(base64.b64decode(result_image))
    except Exception as exc:
        shutil.copyfile(temp_path, destination)
        return False, f"SD WebUI upscaler image decode failed: {exc}"
    return True, None


def build_standalone_realesrgan_command(options: dict, temp_path: Path, destination: Path) -> str:
    exe_path = options.get("realesrganExe", "").strip()
    model_name = options.get("realesrganModel", "").strip() or "realesrgan-x4plus-anime"
    model_dir = options.get("realesrganModelDir", "").strip()
    scale = str(options.get("realesrganScale", "1") or "1").strip()
    tile = str(options.get("realesrganTile", "") or "").strip()
    if not exe_path:
        raise ValueError("Real-ESRGAN executable path is empty.")

    parts = [
        f'"{exe_path}"',
        "-i",
        f'"{temp_path}"',
        "-o",
        f'"{destination}"',
        "-n",
        model_name,
        "-s",
        scale,
    ]
    if model_dir:
        parts.extend(["-m", f'"{model_dir}"'])
    if tile:
        parts.extend(["-t", tile])
    return " ".join(parts)


def run_tagger_command(template: str, image_path: Path, model_name: str = "", timeout: int = 120) -> tuple[list[str], str | None]:
    if not template.strip():
        return [], None
    command = command_with_placeholders(template, {"image": str(image_path), "model": model_name})
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(APP_ROOT),
        )
    except Exception as exc:
        return [], f"tagger command failed: {exc}"

    output = (result.stdout or "").strip()
    if result.returncode != 0:
        err = (result.stderr or output or "unknown error").strip()
        return [], f"tagger command returned {result.returncode}: {err[:500]}"
    return parse_tagger_output(output), None


def load_candidate_tags(
    image_path: Path,
    vocabulary: set[str],
    order_index: dict[str, int],
    eva2_model: str,
    eva2_threshold: float,
    use_sidecar_fallback: bool,
) -> dict:
    raw_tags: list[str] = []
    warnings: list[str] = []
    tag_source = "none"

    eva2_tags, eva2_warning = run_local_eva2_tagger(
        image_path=image_path,
        model_name=eva2_model,
        threshold=eva2_threshold,
    )
    if eva2_warning:
        warnings.append(eva2_warning)
    if eva2_tags:
        raw_tags.extend(eva2_tags)
        tag_source = "local EVA2"

    sidecar = image_path.with_suffix(".txt")
    if use_sidecar_fallback and not raw_tags and sidecar.exists():
        try:
            raw_tags.extend(parse_tags(sidecar.read_text(encoding="utf-8-sig", errors="ignore")))
            tag_source = "sidecar txt"
        except OSError as exc:
            warnings.append(f"could not read sidecar txt: {exc}")

    raw_tags = dedupe(raw_tags)
    if not raw_tags:
        warnings.append("ローカルEVA2でタグを作れませんでした。モデル保存状態としきい値を確認してください。")
    if vocabulary:
        kept = [tag for tag in raw_tags if tag in vocabulary]
        unknown = [tag for tag in raw_tags if tag not in vocabulary]
    else:
        kept = raw_tags
        unknown = []
    kept = sort_tags_by_order(kept, order_index)

    return {
        "tagSource": tag_source,
        "rawTags": raw_tags,
        "keptTags": kept,
        "unknownTags": unknown,
        "warnings": warnings,
    }


def dedupe(tags: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def sort_tags_by_order(tags: list[str], order_index: dict[str, int]) -> list[str]:
    return sorted(tags, key=lambda tag: (order_index.get(tag, 999999), tag))


def create_thumbnail(session_id: str, image_path: Path, index: int) -> str:
    thumb_dir = SESSION_ROOT / session_id / "thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(str(image_path).encode("utf-8")).hexdigest()[:12]
    thumb_name = f"{index:04d}_{digest}.jpg"
    thumb_path = thumb_dir / thumb_name
    if not thumb_path.exists():
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            img.thumbnail((320, 320), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (320, 320), (29, 32, 38))
            x = (320 - img.width) // 2
            y = (320 - img.height) // 2
            canvas.paste(img, (x, y))
            canvas.save(thumb_path, "JPEG", quality=88)
    return f"/api/thumb?session={session_id}&file={thumb_name}"


def create_output_thumbnail(session_id: str, image_path: Path, key: str) -> str:
    """出力PNGそのものからサムネを作る（画面と実ファイルがズレない）。毎回上書き。"""
    thumb_dir = SESSION_ROOT / session_id / "thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    safe_key = re.sub(r"[^A-Za-z0-9_-]+", "_", key)
    thumb_name = f"out_{safe_key}.jpg"
    thumb_path = thumb_dir / thumb_name
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        img.thumbnail((320, 320), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (320, 320), (29, 32, 38))
        canvas.paste(img, ((320 - img.width) // 2, (320 - img.height) // 2))
        canvas.save(thumb_path, "JPEG", quality=88)
    return f"/api/thumb?session={session_id}&file={thumb_name}&v={int(time.time())}"


def preflight_config_from(settings: dict) -> pfc.PreflightConfig:
    return pfc.PreflightConfig(
        sizes=tuple(parse_target_sizes(settings.get("targetSizes", ""))),
        allow_rotate=bool(settings.get("allowRotate", True)),
        pad_crop_x=float(settings.get("padCropX", 0.5)),
        max_crop_frac=float(settings.get("maxCropFrac", 0.15)),
        fullbody_base_height=int(settings.get("fullbodyBaseHeight", 2200)),
        fullbody_tile=int(settings.get("fullbodyTile", 1024)),
        neck_ratio=float(settings.get("neckRatio", 0.14)),
        trim_threshold=int(settings.get("trimThreshold", 18)),
    )


def run_upscaler(temp_path: Path, destination: Path, upscaler_options: dict) -> tuple[bool, str | None]:
    upscaler_mode = (upscaler_options.get("upscalerMode") or "none").strip()
    if upscaler_mode == "sdwebui":
        return run_sd_webui_upscaler(
            temp_path=temp_path,
            destination=destination,
            webui_url=upscaler_options.get("sdWebuiUrl", "http://127.0.0.1:7860"),
            upscaler_name=upscaler_options.get("sdWebuiUpscaler", "R-ESRGAN 4x+ Anime6B"),
        )
    if upscaler_mode == "standalone":
        try:
            command = build_standalone_realesrgan_command(upscaler_options, temp_path, destination)
            return run_subprocess_upscaler(command, temp_path, destination)
        except Exception as exc:
            shutil.copyfile(temp_path, destination)
            return False, str(exc)
    if upscaler_mode == "custom":
        command = command_with_placeholders(
            upscaler_options.get("upscalerCommand", ""),
            {"input": str(temp_path), "output": str(destination)},
        )
        if command.strip():
            return run_subprocess_upscaler(command, temp_path, destination)
        shutil.copyfile(temp_path, destination)
        return False, "Custom upscaler command is empty; upscaler was not run."
    shutil.copyfile(temp_path, destination)
    return False, None


def process_image_v2(
    source: Path,
    dataset_dir: Path,
    stem: str,
    mode: str,
    settings: dict,
    upscaler_options: dict,
    neck_y: float | None = None,
) -> list[dict]:
    """1枚の入力から mode に応じて1枚（通常）または4枚（全身絵）を出力する。

    出力ファイル名: 通常 = {stem}.png / 全身絵 = {stem}_1.png .. {stem}_4.png
    （名前順で 上半身→首から下→足元→全身。TODO_IMAGE_PROCESSING.md の命名案）
    neck_y = 首位置の手動指定（元画像座標。UIのドラッグライン）。
    """
    cfg = preflight_config_from(settings)
    dataset_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[dict] = []
    with Image.open(source) as img:
        img = img.convert("RGB")
        info = pfc.analyze(img, cfg.trim_threshold)
        plans = pfc.plan_for_mode(info, cfg, mode, neck_y=neck_y)
        for index, plan in enumerate(plans, start=1):
            suffix = f"_{index}" if len(plans) > 1 else ""
            destination = dataset_dir / f"{stem}{suffix}.png"
            result = pfc.apply_plan(img, plan)
            temp_path = destination.with_suffix(".pre_upscale.png")
            result.save(temp_path, "PNG")
            applied, warning = run_upscaler(temp_path, destination, upscaler_options)
            try:
                temp_path.unlink()
            except OSError:
                pass
            outputs.append(
                {
                    "image": str(destination),
                    "kind": plan.kind,
                    "kindLabel": pfc.KIND_LABELS.get(plan.kind, plan.kind),
                    "targetSize": f"{plan.scale_to[0]}x{plan.scale_to[1]}",
                    "fallback": plan.fallback,
                    "plan": plan.to_dict(),
                    "upscalerApplied": applied,
                    "upscalerWarning": warning,
                }
            )
    return outputs


def write_prepare_manifest(session: dict, output_dir: Path, dataset_dir: Path) -> None:
    """整形画面の出力台帳。派生元(source)と派生種別(kind)、加工計画(plan)を全部残す。"""
    items = []
    for image in session.get("images", []):
        if not image.get("prepared"):
            continue
        for output in image.get("results", []):
            items.append(
                {
                    "source": image.get("path", ""),
                    "output": output.get("image", ""),
                    "kind": output.get("kind", "normal"),
                    "mode": image.get("mode", "normal"),
                    "targetSize": output.get("targetSize", ""),
                    "fallback": output.get("fallback"),
                    "plan": output.get("plan"),
                    "upscalerApplied": output.get("upscalerApplied", False),
                }
            )
    manifest = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "inputDir": session.get("inputDir", ""),
        "outputDir": str(output_dir),
        "datasetDir": str(dataset_dir),
        "settings": {
            key: session.get("settings", {}).get(key)
            for key in ("targetSizes", "allowRotate", "padCropX", "maxCropFrac", "fullbodyBaseHeight", "fullbodyTile", "neckRatio")
        },
        "items": items,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def build_caption(character_trigger: str, common_tags: list[str], trigger_tokens: list[str], candidate_tags: list[str]) -> str:
    tags = []
    if character_trigger.strip():
        tags.append(character_trigger.strip())
    tags.extend(common_tags)
    tags.extend(trigger_tokens)
    tags.extend(candidate_tags)
    return join_tags(tags)


def read_body(handler: SimpleHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def write_json(handler: SimpleHTTPRequestHandler, data: dict, status: int = 200) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def write_file(handler: SimpleHTTPRequestHandler, path: Path) -> None:
    if not path.exists() or not path.is_file():
        handler.send_error(404)
        return
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
        content_type += "; charset=utf-8"
    data = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class AppHandler(SimpleHTTPRequestHandler):
    server_version = "LoRAPreflight/0.1"

    def log_message(self, fmt: str, *args) -> None:
        safe_print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/":
            write_file(self, STATIC_ROOT / "index.html")
            return
        if path in {"/tagging", "/tagging/"}:
            write_file(self, STATIC_ROOT / "tagging.html")
            return
        if path in {"/dictionary", "/dictionary/"}:
            write_file(self, STATIC_ROOT / "dictionary.html")
            return
        if path.startswith("/static/"):
            rel = path.removeprefix("/static/").lstrip("/")
            write_file(self, STATIC_ROOT / rel)
            return
        if path == "/api/thumb":
            query = parse_qs(parsed.query)
            session_id = query.get("session", [""])[0]
            file_name = Path(query.get("file", [""])[0]).name
            write_file(self, SESSION_ROOT / session_id / "thumbs" / file_name)
            return
        if path == "/api/output":
            # 整形済み出力のフル解像度表示。セッションに記録された出力だけ返す
            query = parse_qs(parsed.query)
            session = self.load_session(query.get("session", [""])[0])
            requested = str(Path(unquote(query.get("path", [""])[0])))
            allowed = {
                str(Path(output["image"]))
                for image in (session or {}).get("images", [])
                for output in image.get("results", [])
            }
            if requested not in allowed:
                self.send_error(403)
                return
            write_file(self, Path(requested))
            return
        if path == "/api/source":
            # 整形対象（元画像）のフル解像度表示。セッションに載っている入力だけ返す
            query = parse_qs(parsed.query)
            session = self.load_session(query.get("session", [""])[0])
            requested = str(Path(unquote(query.get("path", [""])[0])))
            allowed = {str(Path(image["path"])) for image in (session or {}).get("images", [])}
            if requested not in allowed:
                self.send_error(403)
                return
            write_file(self, Path(requested))
            return
        self.send_error(404)

    def do_POST(self) -> None:
        try:
            if self.path == "/api/analyze":
                self.handle_analyze()
            elif self.path == "/api/settings":
                self.handle_settings()
            elif self.path == "/api/tagger/status":
                self.handle_tagger_status()
            elif self.path == "/api/tagger/download":
                self.handle_tagger_download()
            elif self.path == "/api/dictionary":
                self.handle_dictionary()
            elif self.path == "/api/dictionary/build":
                self.handle_dictionary_build()
            elif self.path == "/api/vocabulary/refresh":
                self.handle_vocabulary_refresh()
            elif self.path == "/api/scan":
                self.handle_scan()
            elif self.path == "/api/prepare/scan":
                self.handle_prepare_scan()
            elif self.path == "/api/prepare/image":
                self.handle_prepare_image()
            elif self.path == "/api/pick-folder":
                self.handle_pick_folder()
            elif self.path == "/api/tag/prepare":
                self.handle_tag_prepare()
            elif self.path == "/api/tag/image":
                self.handle_tag_image()
            elif self.path == "/api/build":
                self.handle_build()
            else:
                self.send_error(404)
        except Exception as exc:
            write_json(self, {"ok": False, "error": str(exc)}, status=500)

    def handle_analyze(self) -> None:
        body = read_body(self)
        root = Path(body.get("pastRoot", "")).expanduser()
        write_json(self, analyze_past_captions(root))

    def handle_settings(self) -> None:
        body = read_body(self)
        settings = load_settings()
        if body:
            settings = save_settings(merge_settings(settings, body))
        write_json(
            self,
            {
                "ok": True,
                "settings": settings,
                "dictionary": load_dictionary(),
                "tagger": tagger_model_status(settings.get("eva2Model", "wd-eva02-large-tagger-v3")),
            },
        )

    def handle_tagger_status(self) -> None:
        body = read_body(self)
        settings = merge_settings(load_settings(), body)
        write_json(self, {"ok": True, "tagger": tagger_model_status(settings.get("eva2Model", "wd-eva02-large-tagger-v3"))})

    def handle_tagger_download(self) -> None:
        body = read_body(self)
        settings = save_settings(merge_settings(load_settings(), body))
        status = download_tagger_model(settings.get("eva2Model", "wd-eva02-large-tagger-v3"))
        payload = {"ok": bool(status.get("ok", True)), "settings": settings, "tagger": status}
        if not payload["ok"]:
            payload["error"] = status.get("error", "タグモデルをダウンロードできませんでした。")
        write_json(self, payload)

    def handle_dictionary(self) -> None:
        body = read_body(self)
        tags_text = body.get("tagsText", "")
        if body.get("clear"):
            data = empty_dictionary("辞書未作成")
            write_json(self, save_dictionary(data))
        elif tags_text.strip():
            tags = parse_tags(tags_text)
            data = {
                "ok": True,
                "source": "manual",
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "tags": [{"tag": tag, "count": 1, "avgPosition": index} for index, tag in enumerate(tags)],
                "order": tags,
            }
            write_json(self, save_dictionary(data))
        else:
            write_json(self, load_dictionary())

    def handle_dictionary_build(self) -> None:
        body = read_body(self)
        settings = save_settings(merge_settings(load_settings(), body))
        roots = body.get("vocabularyRoots") or body.get("pastRoot", "")
        if roots:
            settings["vocabularyRoots"] = normalize_roots(roots)
        data = analyze_past_caption_roots(settings.get("vocabularyRoots", []), settings.get("vocabularyMinCount", 1))
        if data.get("ok"):
            data = save_dictionary(data)
        write_json(self, data)

    def handle_vocabulary_refresh(self) -> None:
        body = read_body(self)
        settings = save_settings(merge_settings(load_settings(), body))
        dictionary = refresh_dictionary_from_settings(settings)
        write_json(self, {"ok": True, "settings": settings, "dictionary": dictionary})

    def handle_scan(self) -> None:
        body = read_body(self)
        input_dir = Path(body.get("inputDir", "")).expanduser()
        settings = save_settings(merge_settings(load_settings(), body))
        dictionary = load_dictionary()
        order_index = {tag: index for index, tag in enumerate(dictionary.get("order", []))}

        if not input_dir.exists() or not input_dir.is_dir():
            write_json(self, {"ok": False, "error": "input image folder does not exist"}, status=400)
            return

        session_id = uuid.uuid4().hex[:12]
        (SESSION_ROOT / session_id).mkdir(parents=True, exist_ok=True)
        images = []
        for index, image_path in enumerate(list_images(input_dir), start=1):
            images.append(
                {
                    "id": f"img_{index:04d}",
                    "index": index,
                    "name": image_path.name,
                    "path": str(image_path),
                    "thumbUrl": create_thumbnail(session_id, image_path, index),
                    "tagged": False,
                    "tagSource": "none",
                    "rawTags": [],
                    "keptTags": [],
                    "unknownTags": [],
                    "warnings": [],
                }
            )

        session = {
            "id": session_id,
            "created": time.time(),
            "inputDir": str(input_dir),
            "dictionary": dictionary,
            "settings": settings,
            "orderIndex": order_index,
            "images": images,
        }
        SESSIONS[session_id] = session
        (SESSION_ROOT / session_id / "session.json").write_text(
            json.dumps(session, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_json(
            self,
            {
                "ok": True,
                "sessionId": session_id,
                "images": images,
                "inputDir": str(input_dir),
                "settings": settings,
                "dictionary": dictionary,
            },
        )

    def handle_prepare_scan(self) -> None:
        body = read_body(self)
        input_dir = Path(body.get("inputDir", "")).expanduser()
        settings = save_settings(merge_settings(load_settings(), body))

        if not input_dir.exists() or not input_dir.is_dir():
            write_json(self, {"ok": False, "error": "input image folder does not exist"}, status=400)
            return

        output_dir_raw = body.get("outputDir", "").strip()
        input_parent = input_dir.parent
        if not output_dir_raw:
            output_dir = input_parent / (input_dir.name + "_prepared")
        else:
            output_dir = Path(output_dir_raw).expanduser()
            if not output_dir.is_absolute():
                output_dir = input_parent / output_dir

        session_id = uuid.uuid4().hex[:12]
        (SESSION_ROOT / session_id).mkdir(parents=True, exist_ok=True)
        trim_threshold = int(settings.get("trimThreshold", 18))
        images = []
        for index, image_path in enumerate(list_images(input_dir), start=1):
            # 首ラインの初期位置計算用に寸法と内容範囲も返す
            try:
                with Image.open(image_path) as img:
                    info = pfc.analyze(img.convert("RGB"), trim_threshold)
                size = [info.width, info.height]
                content_box = list(info.content_box)
            except Exception:
                size = None
                content_box = None
            images.append(
                {
                    "id": f"prep_{index:04d}",
                    "index": index,
                    "name": image_path.name,
                    "path": str(image_path),
                    "thumbUrl": create_thumbnail(session_id, image_path, index),
                    "size": size,
                    "contentBox": content_box,
                    "prepared": False,
                    "result": None,
                    "warnings": [],
                }
            )

        session = {
            "id": session_id,
            "type": "prepare",
            "created": time.time(),
            "inputDir": str(input_dir),
            "outputDir": str(output_dir),
            "settings": settings,
            "images": images,
        }
        self.save_session(session)
        write_json(
            self,
            {
                "ok": True,
                "sessionId": session_id,
                "images": images,
                "inputDir": str(input_dir),
                "outputDir": str(output_dir),
                "settings": settings,
            },
        )

    def handle_prepare_image(self) -> None:
        body = read_body(self)
        session_id = body.get("sessionId", "")
        image_id = body.get("imageId", "")
        session = self.load_session(session_id)
        if not session:
            write_json(self, {"ok": False, "error": "session not found. Scan again."}, status=400)
            return

        settings = save_settings(merge_settings(session.get("settings") or load_settings(), body))
        # 出力フォルダはスキャン時でなく整形実行時の値を尊重する
        # （スキャン後に入力・変更しても反映されないバグの修正）
        output_dir_raw = str(body.get("outputDir", "") or "").strip()
        if output_dir_raw:
            output_dir = Path(output_dir_raw).expanduser()
            if not output_dir.is_absolute():
                output_dir = Path(session["inputDir"]).parent / output_dir
            session["outputDir"] = str(output_dir)
        else:
            output_dir = Path(session["outputDir"])
        dataset_dir = output_dir / "images"
        dataset_dir.mkdir(parents=True, exist_ok=True)
        mode = body.get("mode") or "normal"
        neck_y = body.get("neckY")
        try:
            neck_y = float(neck_y) if neck_y is not None else None
        except (TypeError, ValueError):
            neck_y = None
        upscaler_options = {key: settings.get(key, DEFAULT_SETTINGS.get(key)) for key in UPSCALER_KEYS}

        for image in session.get("images", []):
            if image.get("id") != image_id:
                continue
            source = Path(image["path"])
            stem = source.stem
            outputs = process_image_v2(
                source=source,
                dataset_dir=dataset_dir,
                stem=stem,
                mode=mode,
                settings=settings,
                upscaler_options=upscaler_options,
                neck_y=neck_y,
            )
            for out_index, output in enumerate(outputs, start=1):
                output["thumbUrl"] = create_output_thumbnail(
                    session_id, Path(output["image"]), f"{image['id']}_{out_index}"
                )
            image["prepared"] = True
            image["mode"] = mode
            image["results"] = outputs
            image["result"] = outputs[0]
            image["warnings"] = [
                f"{Path(o['image']).name}: {o['upscalerWarning']}" for o in outputs if o.get("upscalerWarning")
            ] + [f"{Path(o['image']).name}: {o['fallback']}" for o in outputs if o.get("fallback")]
            session["settings"] = settings
            self.save_session(session)
            write_prepare_manifest(session, output_dir, dataset_dir)
            write_json(self, {"ok": True, "image": image, "outputDir": str(output_dir), "datasetDir": str(dataset_dir)})
            return

        write_json(self, {"ok": False, "error": "image not found. Scan again."}, status=400)

    def load_session(self, session_id: str) -> dict | None:
        session = SESSIONS.get(session_id)
        if not session:
            session_path = SESSION_ROOT / session_id / "session.json"
            if session_path.exists():
                session = json.loads(session_path.read_text(encoding="utf-8"))
                SESSIONS[session_id] = session
        return session

    def save_session(self, session: dict) -> None:
        session_id = session["id"]
        SESSIONS[session_id] = session
        (SESSION_ROOT / session_id).mkdir(parents=True, exist_ok=True)
        (SESSION_ROOT / session_id / "session.json").write_text(
            json.dumps(session, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def handle_pick_folder(self) -> None:
        """OSのフォルダ選択ダイアログを開いて選択パスを返す（ローカル専用ツール前提）。"""
        body = read_body(self)
        initial = str(body.get("initial", "") or "").strip()
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            kwargs = {}
            if initial:
                candidate = Path(initial).expanduser()
                if candidate.is_dir():
                    kwargs["initialdir"] = str(candidate)
            selected = filedialog.askdirectory(parent=root, title="フォルダを選択", **kwargs)
            root.destroy()
        except Exception as exc:
            write_json(
                self,
                {"ok": False, "error": f"フォルダ選択ダイアログを開けませんでした。パスを直接入力してください。({exc})"},
                status=500,
            )
            return
        write_json(self, {"ok": True, "path": str(Path(selected)) if selected else ""})

    def handle_tag_prepare(self) -> None:
        body = read_body(self)
        session_id = body.get("sessionId", "")
        session = self.load_session(session_id)
        if not session:
            write_json(self, {"ok": False, "error": "session not found. Scan again."}, status=400)
            return

        settings = save_settings(merge_settings(load_settings(), body))
        if settings.get("autoVocabularyRefresh"):
            dictionary = refresh_dictionary_from_settings(settings)
        else:
            dictionary = load_dictionary()
        order_index = {tag: index for index, tag in enumerate(dictionary.get("order", []))}
        session["dictionary"] = dictionary
        session["settings"] = settings
        session["orderIndex"] = order_index
        self.save_session(session)
        write_json(
            self,
            {
                "ok": True,
                "settings": settings,
                "dictionary": dictionary,
                "tagger": tagger_model_status(settings.get("eva2Model", "wd-eva02-large-tagger-v3")),
            },
        )

    def handle_tag_image(self) -> None:
        body = read_body(self)
        session_id = body.get("sessionId", "")
        image_id = body.get("imageId", "")
        session = self.load_session(session_id)
        if not session:
            write_json(self, {"ok": False, "error": "session not found. Scan again."}, status=400)
            return

        settings = session.get("settings") or load_settings()
        dictionary = session.get("dictionary") or load_dictionary()
        vocabulary = {item["tag"] for item in dictionary.get("tags", [])}
        order_index = {tag: index for index, tag in enumerate(dictionary.get("order", []))}
        eva2_model = settings.get("eva2Model", "wd-eva02-large-tagger-v3")
        eva2_threshold = float(settings.get("eva2Threshold", 0.35) or 0.35)
        use_sidecar_fallback = settings.get("useSidecarFallback", True)

        for image in session.get("images", []):
            if image.get("id") != image_id:
                continue
            candidate = load_candidate_tags(
                image_path=Path(image["path"]),
                vocabulary=vocabulary,
                order_index=order_index,
                eva2_model=eva2_model,
                eva2_threshold=eva2_threshold,
                use_sidecar_fallback=use_sidecar_fallback,
            )
            image.update(candidate)
            image["tagged"] = True
            self.save_session(session)
            write_json(
                self,
                {
                    "ok": True,
                    "image": image,
                    "dictionary": dictionary,
                    "tagger": tagger_model_status(eva2_model),
                },
            )
            return

        write_json(self, {"ok": False, "error": "image not found. Scan again."}, status=400)

    def handle_build(self) -> None:
        body = read_body(self)
        session_id = body.get("sessionId", "")
        session = self.load_session(session_id)
        if not session:
            write_json(self, {"ok": False, "error": "session not found. Scan again."}, status=400)
            return

        output_dir_raw = body.get("outputDir", "").strip()
        input_parent = Path(session["inputDir"]).parent
        if not output_dir_raw:
            output_dir = input_parent / (Path(session["inputDir"]).name + "_preflight")
        else:
            output_dir = Path(output_dir_raw).expanduser()
            if not output_dir.is_absolute():
                output_dir = input_parent / output_dir
        dataset_dir = output_dir / "dataset"
        dataset_dir.mkdir(parents=True, exist_ok=True)

        character_trigger = body.get("characterTrigger", "")
        common_tags = parse_tags(body.get("commonTags", ""))
        assignments = body.get("assignments", {})
        modes = body.get("modes", {}) if isinstance(body.get("modes"), dict) else {}
        neck_ys = body.get("neckYs", {}) if isinstance(body.get("neckYs"), dict) else {}
        trigger_definitions = body.get("triggerDefinitions", [])
        token_by_id = {item.get("id"): item.get("token", "").strip() for item in trigger_definitions}
        settings = merge_settings(load_settings(), body)
        target_sizes = parse_target_sizes(settings.get("targetSizes", ""))
        allow_rotate = bool(settings.get("allowRotate", True))
        upscaler_options = {key: settings.get(key, DEFAULT_SETTINGS.get(key)) for key in UPSCALER_KEYS}

        results = []
        warnings = []
        for index, image in enumerate(session["images"], start=1):
            source = Path(image["path"])
            stem = f"{index:03d}"
            mode = modes.get(image["id"]) or image.get("mode") or "normal"
            try:
                neck_y = float(neck_ys[image["id"]]) if image["id"] in neck_ys else None
            except (TypeError, ValueError):
                neck_y = None
            selected_ids = assignments.get(image["id"], [])
            trigger_tokens = [token_by_id.get(trigger_id, "") for trigger_id in selected_ids]
            trigger_tokens = [token for token in trigger_tokens if token]

            outputs = process_image_v2(
                source=source,
                dataset_dir=dataset_dir,
                stem=stem,
                mode=mode,
                settings=settings,
                upscaler_options=upscaler_options,
                neck_y=neck_y,
            )
            for output in outputs:
                image_out = Path(output["image"])
                txt_out = image_out.with_suffix(".txt")
                # 首から下の派生画像には head out of frame を足す（TODOの構図意図）
                extra = ["head out of frame"] if output["kind"] == "fb_body" else []
                caption = build_caption(
                    character_trigger, common_tags, trigger_tokens, extra + image.get("keptTags", [])
                )
                txt_out.write_text(caption, encoding="utf-8")
                result = {
                    "source": str(source),
                    "image": str(image_out),
                    "captionFile": str(txt_out),
                    "caption": caption,
                    "kind": output["kind"],
                    "mode": mode,
                    "targetSize": output["targetSize"],
                    "fallback": output.get("fallback"),
                    "plan": output.get("plan"),
                    "upscalerApplied": output.get("upscalerApplied", False),
                    "upscalerWarning": output.get("upscalerWarning"),
                }
                if output.get("upscalerWarning"):
                    warnings.append(f"{image_out.name}: {output['upscalerWarning']}")
                if output.get("fallback"):
                    warnings.append(f"{image_out.name}: {output['fallback']}")
                results.append(result)

        manifest = {
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "inputDir": session["inputDir"],
            "outputDir": str(output_dir),
            "datasetDir": str(dataset_dir),
            "targetSizes": [f"{w}x{h}" for w, h in target_sizes],
            "allowRotate": allow_rotate,
            "padCropX": settings.get("padCropX"),
            "maxCropFrac": settings.get("maxCropFrac"),
            "fullbodyBaseHeight": settings.get("fullbodyBaseHeight"),
            "fullbodyTile": settings.get("fullbodyTile"),
            "neckRatio": settings.get("neckRatio"),
            "upscalerOptions": {
                key: value for key, value in upscaler_options.items() if key != "upscalerCommand" or value
            },
            "characterTrigger": character_trigger,
            "commonTags": common_tags,
            "triggerDefinitions": trigger_definitions,
            "warnings": warnings,
            "items": results,
            "nextStep": "AI Toolkit start button is intentionally a placeholder in this version.",
        }
        (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / "dictionary_summary.json").write_text(
            json.dumps(session.get("dictionary", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_json(
            self,
            {
                "ok": True,
                "outputDir": str(output_dir),
                "datasetDir": str(dataset_dir),
                "count": len(results),
                "warnings": warnings,
                "manifest": str(output_dir / "manifest.json"),
            },
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="LoRA Preflight local web UI")
    parser.add_argument("--port", type=int, default=int(os.environ.get("LORA_PREFLIGHT_PORT", "7869")))
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    args = parser.parse_args()

    port = args.port
    host = "127.0.0.1"
    server = ThreadingHTTPServer((host, port), AppHandler)
    url = f"http://{host}:{port}/"
    safe_print(f"LoRA Preflight UI: {url}")
    safe_print("Press Ctrl+C to stop.")
    if not args.no_browser and os.environ.get("LORA_PREFLIGHT_NO_BROWSER") != "1":
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        safe_print("\nStopping.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

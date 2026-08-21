# Recuperación: Estudio de IA local (borrado el 2026-08-18)

Este documento contiene todo lo necesario para reconstruir desde cero el proyecto que existía en
`C:\jfrodriguezv\SourceCodeAnthropic\Generativa\ia-imagenes\` antes de ser eliminado a petición del usuario.

Todo el código fuente (`app.py`, `workflows.py`, `comfy_client.py`, `index.html`) está incluido completo
más abajo — no depende de ningún repositorio externo para recuperarse.

---

## 1. Qué se había construido

Un portal web de chat local (Flask) que habla con ComfyUI (motor de inferencia) para:
- **Generar imagen** desde texto (SDXL base 1.0) — probado y funcionando
- **Editar imagen** manteniendo identidad: ropa, pose, cuerpo (Qwen-Image-Edit) — modelos descargados, prueba end-to-end en curso al momento del borrado
- **Video experimental** desde una imagen (LTX-Video) — código listo, sin probar

Ver el documento de arquitectura publicado como Artifact para el detalle completo de diseño (diagramas,
patrones, flujo de datos): fue generado en esta misma conversación, pídele a Claude que lo recupere de la
lista de artifacts si lo necesitas de nuevo.

## 2. Hardware de referencia (para las decisiones que se tomaron)

- Intel Core Ultra 5 135U, gráficos integrados (**sin GPU dedicada**)
- 32GB RAM
- Windows 11 Pro
- Por esto: todo corre en **CPU**, generación de imagen ~5-20 min, edición potencialmente 30 min-varias horas

## 3. Pasos exactos para reinstalar todo

```powershell
# 1. Crear carpeta y entorno virtual (Python 3.12, no 3.13/3.14 por compatibilidad con torch)
mkdir C:\jfrodriguezv\SourceCodeAnthropic\Generativa\ia-imagenes
cd C:\jfrodriguezv\SourceCodeAnthropic\Generativa\ia-imagenes
py -3.12 -m venv .venv

# 2. Clonar ComfyUI
git clone https://github.com/comfyanonymous/ComfyUI.git

# 3. Instalar PyTorch CPU
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# 4. Instalar dependencias de ComfyUI
cd ComfyUI
..\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 5. Instalar el nodo GGUF (necesario para Qwen-Image-Edit cuantizado)
cd custom_nodes
git clone https://github.com/city96/ComfyUI-GGUF.git
cd ComfyUI-GGUF
..\..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..\..\..

# 6. Instalar dependencias del portal
.\.venv\Scripts\python.exe -m pip install flask requests websocket-client
```

### Nota sobre curl y SSL en esta red corporativa

Si usas `curl.exe` para descargar los modelos, esta red (dominio `truper.com.mx`) provoca fallos de
verificación de revocación de certificado. Solución: agregar la bandera `--ssl-no-revoke` a todos los
comandos curl, ej:
```powershell
curl.exe -L --ssl-no-revoke --retry 8 --retry-delay 5 -o "archivo.safetensors" "https://..."
```

## 4. Modelos a descargar (ninguno requiere cuenta ni licencia)

| Archivo | Destino | Fuente | Tamaño |
|---|---|---|---|
| `sd_xl_base_1.0.safetensors` | `ComfyUI\models\checkpoints\` | `https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors` | 6.9 GB |
| `t5xxl_fp8_e4m3fn.safetensors` | `ComfyUI\models\clip\` | `https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors` | 4.9 GB |
| `clip_l.safetensors` | `ComfyUI\models\clip\` | `https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors` | 246 MB |
| `ltxv-2b-0.9.8-distilled-fp8.safetensors` | `ComfyUI\models\checkpoints\` | `https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltxv-2b-0.9.8-distilled-fp8.safetensors` | 4.5 GB |
| `Qwen_Image_Edit-Q4_K_M.gguf` | `ComfyUI\models\unet\` | `https://huggingface.co/QuantStack/Qwen-Image-Edit-GGUF/resolve/main/Qwen_Image_Edit-Q4_K_M.gguf` | 12.2 GB |
| `Qwen_Image-VAE.safetensors` | `ComfyUI\models\vae\` | `https://huggingface.co/QuantStack/Qwen-Image-Edit-GGUF/resolve/main/VAE/Qwen_Image-VAE.safetensors` | 254 MB |
| `qwen_2.5_vl_7b_fp8_scaled.safetensors` | `ComfyUI\models\clip\` | `https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors` | 9.4 GB |

**Total: ~38.4 GB.** Verifica espacio en disco antes de empezar.

> Nota histórica: se evaluó primero FLUX.1 Kontext para el modo de edición, pero requiere cuenta y
> aceptar licencia en Hugging Face (gated). Se reemplazó por Qwen-Image-Edit (Apache 2.0, sin gating)
> a petición explícita del usuario de no depender de licencias.

## 5. Código fuente completo

Recrea esta estructura dentro de `ia-imagenes\portal\`:
```
portal\
├── app.py
├── comfy_client.py
├── workflows.py
├── templates\
│   └── index.html
└── static\
    ├── uploads\   (vacía, se llena en uso)
    └── outputs\   (vacía, se llena en uso)
```

### `portal/comfy_client.py`

```python
import json
import time
import uuid
import urllib.request

COMFY_URL = "http://127.0.0.1:8188"


def queue_prompt(workflow: dict) -> str:
    client_id = str(uuid.uuid4())
    data = json.dumps({"prompt": workflow, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(f"{COMFY_URL}/prompt", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    return result["prompt_id"]


def wait_for_result(prompt_id: str, timeout: int = 7200, poll_interval: float = 2.0):
    start = time.time()
    consecutive_errors = 0
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{COMFY_URL}/history/{prompt_id}") as resp:
                history = json.loads(resp.read())
            consecutive_errors = 0
        except (OSError, ConnectionError) as e:
            consecutive_errors += 1
            if consecutive_errors > 20:
                raise ConnectionError(f"Se perdió la conexión con ComfyUI de forma persistente: {e}")
            time.sleep(poll_interval)
            continue
        if prompt_id in history:
            outputs = history[prompt_id]["outputs"]
            return outputs
        time.sleep(poll_interval)
    raise TimeoutError("La generación tardó demasiado y se agotó el tiempo de espera.")


def extract_images(outputs: dict):
    images = []
    for node_output in outputs.values():
        if "images" in node_output:
            for img in node_output["images"]:
                images.append(img)
    return images


def extract_videos(outputs: dict):
    videos = []
    for node_output in outputs.values():
        for key in ("videos", "gifs"):
            if key in node_output:
                for v in node_output[key]:
                    videos.append(v)
    return videos


def upload_image(filepath: str, filename: str) -> str:
    boundary = uuid.uuid4().hex
    with open(filepath, "rb") as f:
        file_content = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + file_content + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"{COMFY_URL}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    return result["name"]


def image_url(filename: str, subfolder: str = "", img_type: str = "output") -> str:
    return f"{COMFY_URL}/view?filename={filename}&subfolder={subfolder}&type={img_type}"
```

### `portal/workflows.py`

```python
import random


def txt2img_sdxl(prompt: str, negative: str = "blurry, low quality, deformed, watermark, text, bad anatomy",
                  width: int = 1024, height: int = 1024, steps: int = 35, seed: int | None = None) -> dict:
    if seed is None:
        seed = random.randint(0, 2**32 - 1)
    return {
        "4": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative, "clip": ["4", 1]}},
        "3": {"class_type": "KSampler",
              "inputs": {
                  "seed": seed, "steps": steps, "cfg": 7.0,
                  "sampler_name": "dpmpp_2m", "scheduler": "normal", "denoise": 1.0,
                  "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0],
                  "latent_image": ["5", 0],
              }},
        "8": {"class_type": "VAEDecode",
              "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": "portal_gen", "images": ["8", 0]}},
    }


def qwen_image_edit(image_filename: str, instruction: str, steps: int = 20, seed: int | None = None) -> dict:
    if seed is None:
        seed = random.randint(0, 2**32 - 1)
    return {
        "1": {"class_type": "UnetLoaderGGUF",
              "inputs": {"unet_name": "Qwen_Image_Edit-Q4_K_M.gguf"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image"}},
        "3": {"class_type": "VAELoader",
              "inputs": {"vae_name": "Qwen_Image-VAE.safetensors"}},
        "4": {"class_type": "LoadImage",
              "inputs": {"image": image_filename}},
        "5": {"class_type": "TextEncodeQwenImageEdit",
              "inputs": {"clip": ["2", 0], "vae": ["3", 0], "image": ["4", 0], "prompt": instruction}},
        "6": {"class_type": "TextEncodeQwenImageEdit",
              "inputs": {"clip": ["2", 0], "vae": ["3", 0], "image": ["4", 0], "prompt": "low quality, blurry, distorted, watermark"}},
        "7": {"class_type": "VAEEncode",
              "inputs": {"pixels": ["4", 0], "vae": ["3", 0]}},
        "8": {"class_type": "KSampler",
              "inputs": {
                  "seed": seed, "steps": steps, "cfg": 2.5,
                  "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
                  "model": ["1", 0], "positive": ["5", 0], "negative": ["6", 0],
                  "latent_image": ["7", 0],
              }},
        "9": {"class_type": "VAEDecode",
              "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage",
               "inputs": {"filename_prefix": "portal_edit", "images": ["9", 0]}},
    }


def img2video_ltx(image_filename: str, prompt: str,
                   negative: str = "blurry, low quality, distorted, static, watermark",
                   width: int = 768, height: int = 512, length: int = 97, fps: float = 24.0,
                   steps: int = 30, seed: int | None = None) -> dict:
    if seed is None:
        seed = random.randint(0, 2**32 - 1)
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "ltxv-2b-0.9.8-distilled-fp8.safetensors"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": "t5xxl_fp8_e4m3fn.safetensors", "type": "ltxv"}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["2", 0]}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative, "clip": ["2", 0]}},
        "5": {"class_type": "LoadImage",
              "inputs": {"image": image_filename}},
        "6": {"class_type": "LTXVImgToVideo",
              "inputs": {
                  "positive": ["3", 0], "negative": ["4", 0], "vae": ["1", 2],
                  "image": ["5", 0], "width": width, "height": height,
                  "length": length, "batch_size": 1, "strength": 1.0,
              }},
        "7": {"class_type": "ModelSamplingLTXV",
              "inputs": {"model": ["1", 0], "max_shift": 2.05, "base_shift": 0.95, "latent": ["6", 2]}},
        "8": {"class_type": "KSampler",
              "inputs": {
                  "seed": seed, "steps": steps, "cfg": 3.0,
                  "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                  "model": ["7", 0], "positive": ["6", 0], "negative": ["6", 1],
                  "latent_image": ["6", 2],
              }},
        "9": {"class_type": "VAEDecode",
              "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
        "10": {"class_type": "CreateVideo",
               "inputs": {"images": ["9", 0], "fps": fps}},
        "11": {"class_type": "SaveVideo",
               "inputs": {"video": ["10", 0], "filename_prefix": "portal_video", "format": "mp4"}},
    }
```

### `portal/app.py`

```python
import os
import shutil
import threading
import time
import uuid

from flask import Flask, request, jsonify, render_template, send_from_directory

import comfy_client
import workflows

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "static", "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__)

jobs = {}


def run_job(job_id: str, mode: str, prompt: str, image_path: str | None):
    jobs[job_id] = {"status": "running", "started": time.time()}
    try:
        if mode == "generate":
            wf = workflows.txt2img_sdxl(prompt)
        elif mode == "edit":
            comfy_filename = comfy_client.upload_image(image_path, os.path.basename(image_path))
            wf = workflows.qwen_image_edit(comfy_filename, prompt)
        elif mode == "video":
            comfy_filename = comfy_client.upload_image(image_path, os.path.basename(image_path))
            wf = workflows.img2video_ltx(comfy_filename, prompt)
        else:
            raise ValueError(f"Modo desconocido: {mode}")

        prompt_id = comfy_client.queue_prompt(wf)
        outputs = comfy_client.wait_for_result(prompt_id, timeout=10800)

        images = comfy_client.extract_images(outputs)
        videos = comfy_client.extract_videos(outputs)

        result_files = []
        for img in images:
            url = comfy_client.image_url(img["filename"], img.get("subfolder", ""), img.get("type", "output"))
            local_name = f"{job_id}_{img['filename']}"
            local_path = os.path.join(OUTPUT_DIR, local_name)
            _download(url, local_path)
            result_files.append({"type": "image", "url": f"/static/outputs/{local_name}"})

        for vid in videos:
            url = comfy_client.image_url(vid["filename"], vid.get("subfolder", ""), vid.get("type", "output"))
            local_name = f"{job_id}_{vid['filename']}"
            local_path = os.path.join(OUTPUT_DIR, local_name)
            _download(url, local_path)
            result_files.append({"type": "video", "url": f"/static/outputs/{local_name}"})

        jobs[job_id] = {"status": "done", "files": result_files, "started": jobs[job_id]["started"]}
    except Exception as e:
        jobs[job_id] = {"status": "error", "error": str(e), "started": jobs[job_id]["started"]}


def _download(url: str, dest: str):
    import urllib.request
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    mode = request.form.get("mode", "generate")
    prompt = request.form.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Escribe una descripción o instrucción."}), 400

    image_path = None
    if "image" in request.files and request.files["image"].filename:
        file = request.files["image"]
        ext = os.path.splitext(file.filename)[1] or ".png"
        image_name = f"{uuid.uuid4().hex}{ext}"
        image_path = os.path.join(UPLOAD_DIR, image_name)
        file.save(image_path)

    if mode in ("edit", "video") and not image_path:
        return jsonify({"error": "Este modo requiere que subas una imagen."}), 400

    job_id = uuid.uuid4().hex
    thread = threading.Thread(target=run_job, args=(job_id, mode, prompt, image_path), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "unknown"}), 404
    elapsed = int(time.time() - job["started"])
    return jsonify({**job, "elapsed": elapsed})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
```

### `portal/templates/index.html`

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Estudio de IA local</title>
<style>
  :root {
    --bg: #0f1115; --panel: #171a21; --panel2: #1f232c; --text: #e8e9ec;
    --muted: #8b8f9a; --accent: #6c5ce7; --accent2: #00d4a3; --bubble-user: #2b2f3a;
    --border: #2a2e38;
  }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui, -apple-system, Segoe UI, sans-serif; background: var(--bg); color: var(--text); height:100vh; display:flex; }
  .sidebar { width: 230px; background: var(--panel); border-right:1px solid var(--border); padding: 20px; display:flex; flex-direction:column; gap:10px; }
  .sidebar h1 { font-size: 16px; margin: 0 0 16px; color: var(--accent2); }
  .mode-btn { padding: 12px; border-radius: 10px; border: 1px solid var(--border); background: var(--panel2); color: var(--text); cursor:pointer; text-align:left; font-size: 14px; }
  .mode-btn.active { border-color: var(--accent); background: linear-gradient(135deg, #6c5ce7 0%, #00d4a3 150%); color: #fff; }
  .mode-desc { font-size: 12px; color: var(--muted); margin-top: -6px; }
  .main { flex:1; display:flex; flex-direction:column; }
  .chat { flex:1; overflow-y:auto; padding: 24px; display:flex; flex-direction:column; gap:16px; }
  .msg { max-width: 640px; padding: 14px 16px; border-radius: 14px; line-height:1.4; }
  .msg.user { align-self:flex-end; background: var(--bubble-user); }
  .msg.bot { align-self:flex-start; background: var(--panel2); border: 1px solid var(--border); }
  .msg img, .msg video { max-width: 100%; border-radius: 10px; margin-top: 8px; display:block; }
  .thumb { max-width: 160px; border-radius: 8px; margin-top: 6px; }
  .status-line { font-size: 13px; color: var(--muted); display:flex; align-items:center; gap:8px; }
  .spinner { width:14px; height:14px; border:2px solid var(--border); border-top-color: var(--accent2); border-radius:50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .composer { border-top: 1px solid var(--border); padding: 16px 24px; background: var(--panel); }
  .preview-row { display:flex; gap:10px; margin-bottom: 10px; }
  .preview-row img { height: 60px; border-radius: 8px; border:1px solid var(--border); }
  .input-row { display:flex; gap:10px; align-items:flex-end; }
  textarea { flex:1; resize:none; background: var(--panel2); color: var(--text); border:1px solid var(--border); border-radius: 12px; padding: 12px 14px; font-size:14px; font-family: inherit; }
  button.send { background: var(--accent); color:#fff; border:none; border-radius: 12px; padding: 12px 20px; cursor:pointer; font-size:14px; }
  button.send:disabled { opacity:0.5; cursor:not-allowed; }
  label.upload { background: var(--panel2); border:1px dashed var(--border); border-radius: 12px; padding: 12px 14px; cursor:pointer; font-size: 13px; color: var(--muted); white-space:nowrap; }
  input[type=file] { display:none; }
  .hint { font-size: 12px; color: var(--muted); margin-top: 8px; }
</style>
</head>
<body>

<div class="sidebar">
  <h1>🎨 Estudio de IA local</h1>
  <div class="mode-btn active" data-mode="generate">Generar imagen
    <div class="mode-desc">Describe una escena desde cero</div>
  </div>
  <div class="mode-btn" data-mode="edit">Editar imagen
    <div class="mode-desc">Sube una foto y describe el cambio</div>
  </div>
  <div class="mode-btn" data-mode="video">Video (experimental)
    <div class="mode-desc">Sube una foto y descríbela en movimiento</div>
  </div>
  <div class="hint">Todo corre 100% local en tu equipo. Sin límite de contenido, sin conexión externa. Los tiempos pueden ser largos (minutos a horas) porque no hay GPU dedicada.</div>
</div>

<div class="main">
  <div class="chat" id="chat">
    <div class="msg bot">Hola. Elige un modo a la izquierda y descríbeme lo que quieres crear o editar.</div>
  </div>
  <div class="composer">
    <div class="preview-row" id="previewRow" style="display:none;"></div>
    <div class="input-row">
      <label class="upload" id="uploadLabel" style="display:none;">
        📎 Subir imagen
        <input type="file" id="fileInput" accept="image/*">
      </label>
      <textarea id="promptInput" rows="2" placeholder="Ej: retrato ultra detallado de un lobo en la nieve, luz dramática, 8k"></textarea>
      <button class="send" id="sendBtn">Enviar</button>
    </div>
  </div>
</div>

<script>
let mode = "generate";
let selectedFile = null;

const modeBtns = document.querySelectorAll(".mode-btn");
const uploadLabel = document.getElementById("uploadLabel");
const fileInput = document.getElementById("fileInput");
const previewRow = document.getElementById("previewRow");
const chat = document.getElementById("chat");
const promptInput = document.getElementById("promptInput");
const sendBtn = document.getElementById("sendBtn");

modeBtns.forEach(btn => {
  btn.addEventListener("click", () => {
    modeBtns.forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    mode = btn.dataset.mode;
    uploadLabel.style.display = (mode === "edit" || mode === "video") ? "block" : "none";
    if (mode === "generate") { selectedFile = null; previewRow.style.display = "none"; previewRow.innerHTML = ""; }
    const placeholders = {
      generate: "Ej: retrato ultra detallado de un lobo en la nieve, luz dramática, 8k",
      edit: "Ej: ponme una camisa roja y súbeme los brazos como si estuviera bailando",
      video: "Ej: que la persona baile de forma alegre, cámara fija"
    };
    promptInput.placeholder = placeholders[mode];
  });
});

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) {
    selectedFile = fileInput.files[0];
    const url = URL.createObjectURL(selectedFile);
    previewRow.style.display = "flex";
    previewRow.innerHTML = `<img src="${url}">`;
  }
});

function addMsg(html, cls) {
  const div = document.createElement("div");
  div.className = "msg " + cls;
  div.innerHTML = html;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

async function send() {
  const prompt = promptInput.value.trim();
  if (!prompt) return;
  if ((mode === "edit" || mode === "video") && !selectedFile) {
    addMsg("Este modo necesita que subas una imagen primero.", "bot");
    return;
  }

  let userHtml = prompt;
  if (selectedFile) {
    const url = URL.createObjectURL(selectedFile);
    userHtml += `<br><img class="thumb" src="${url}">`;
  }
  addMsg(userHtml, "user");
  promptInput.value = "";
  sendBtn.disabled = true;

  const statusMsg = addMsg(`<div class="status-line"><div class="spinner"></div><span id="statusText">Iniciando generación...</span></div>`, "bot");
  const statusText = statusMsg.querySelector("#statusText");

  const form = new FormData();
  form.append("mode", mode);
  form.append("prompt", prompt);
  if (selectedFile) form.append("image", selectedFile);

  try {
    const res = await fetch("/api/chat", { method: "POST", body: form });
    const data = await res.json();
    if (data.error) {
      statusMsg.innerHTML = "⚠️ " + data.error;
      sendBtn.disabled = false;
      return;
    }
    pollStatus(data.job_id, statusMsg, statusText);
  } catch (e) {
    statusMsg.innerHTML = "⚠️ Error de conexión con el portal.";
    sendBtn.disabled = false;
  }
}

async function pollStatus(jobId, statusMsg, statusText) {
  const res = await fetch(`/api/status/${jobId}`);
  const data = await res.json();

  if (data.status === "running") {
    const mins = Math.floor(data.elapsed / 60);
    const secs = data.elapsed % 60;
    statusText.textContent = `Generando... (${mins}m ${secs}s transcurridos, puede tardar bastante en CPU)`;
    setTimeout(() => pollStatus(jobId, statusMsg, statusText), 3000);
  } else if (data.status === "done") {
    let html = "Listo:";
    for (const f of data.files) {
      if (f.type === "image") html += `<img src="${f.url}">`;
      else if (f.type === "video") html += `<video src="${f.url}" controls></video>`;
    }
    statusMsg.innerHTML = html;
    sendBtn.disabled = false;
  } else if (data.status === "error") {
    statusMsg.innerHTML = "⚠️ Error: " + data.error;
    sendBtn.disabled = false;
  } else {
    setTimeout(() => pollStatus(jobId, statusMsg, statusText), 3000);
  }
}

sendBtn.addEventListener("click", send);
promptInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
</script>
</body>
</html>
```

## 6. Cómo arrancar una vez reinstalado

```powershell
# Terminal 1: ComfyUI
cd C:\jfrodriguezv\SourceCodeAnthropic\Generativa\ia-imagenes\ComfyUI
..\.venv\Scripts\python.exe main.py --cpu

# Terminal 2 (esperar a que el terminal 1 diga "To see the GUI go to: http://127.0.0.1:8188"):
cd C:\jfrodriguezv\SourceCodeAnthropic\Generativa\ia-imagenes\portal
..\.venv\Scripts\python.exe app.py
```
Luego abrir `http://127.0.0.1:5050` en el navegador.

## 7. Problemas conocidos y sus soluciones

- **`WinError 10013` / cortes de red intermitentes**: ya solucionado en `comfy_client.py` con reintentos
  (hasta 20, cada 2s) antes de dar error definitivo — código ya incluido arriba.
- **Los servidores se caen solos entre sesiones largas de Claude Code**: si el proceso host que maneja
  los procesos en segundo plano se recicla, ComfyUI y Flask mueren sin dejar log de error. Solución:
  simplemente reiniciar ambos con los comandos de la sección 6.
- **Puerto 8188 "ya en uso" al reiniciar**: significa que ya hay un ComfyUI corriendo (revisar con
  `netstat -ano | findstr 8188` antes de lanzar uno nuevo).

## 8. Pendiente al momento del borrado

- La prueba automática de extremo a extremo de "Editar imagen" (Qwen-Image-Edit) estaba en curso;
  no se confirmó el resultado final antes de borrar todo.
- El modo "Video" (LTX-Video) nunca se probó con una generación real.

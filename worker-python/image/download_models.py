"""Descarga automática de los modelos auxiliares que no se bajan solos desde diffusers:
- Escalado Full HD: `worker-python/upscale-models/FSRCNN_x4.pb`
- Restauración facial: `worker-python/faceswap-models/GFPGANv1.4.pth`
- Face-swap: `worker-python/faceswap-models/inswapper_128.onnx`

Uso:
    python worker-python/image/download_models.py
"""

import os
import ssl
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACESWAP_DIR = os.environ.get(
    "GENERATIVA_FACESWAP_MODELS_ROOT",
    os.path.join(BASE_DIR, "faceswap-models"),
)
UPSCALE_DIR = os.path.join(BASE_DIR, "upscale-models")

MODELS = [
    {
        "name": "FSRCNN_x4.pb (Escalado Full HD)",
        "dest": os.path.join(UPSCALE_DIR, "FSRCNN_x4.pb"),
        "min_bytes": 20_000,
        "urls": [
            "https://github.com/Saafke/FSRCNN_Tensorflow/raw/master/models/FSRCNN_x4.pb",
            "https://raw.githubusercontent.com/Saafke/FSRCNN_Tensorflow/master/models/FSRCNN_x4.pb",
        ],
    },
    {
        "name": "GFPGANv1.4.pth (Restauración facial GFPGAN)",
        "dest": os.path.join(FACESWAP_DIR, "GFPGANv1.4.pth"),
        "min_bytes": 300_000_000,
        "urls": [
            "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth",
            "https://huggingface.co/gmk123/GFPGAN/resolve/main/GFPGANv1.4.pth",
        ],
    },
    {
        "name": "inswapper_128.onnx (Intercambio de rostro InsightFace)",
        "dest": os.path.join(FACESWAP_DIR, "inswapper_128.onnx"),
        "min_bytes": 500_000_000,
        "urls": [
            "https://huggingface.co/ezioruan/inswapper_128.onnx/resolve/main/inswapper_128.onnx",
            "https://huggingface.co/deepinsight/inswapper/resolve/main/inswapper_128.onnx",
        ],
    },
]


def _download_file(url: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp_dest = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Generativa-Downloader)"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=120) as resp, open(tmp_dest, "wb") as out:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024  # 1 MB
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded * 100 / total
                print(f"\r  -> {downloaded / (1024 * 1024):.1f} / {total / (1024 * 1024):.1f} MB ({pct:.0f}%)", end="", flush=True)
        if total > 0:
            print()
    os.replace(tmp_dest, dest)


def ensure_models() -> None:
    for item in MODELS:
        dest = item["dest"]
        name = item["name"]
        min_bytes = item["min_bytes"]

        if os.path.isfile(dest) and os.path.getsize(dest) >= min_bytes:
            size_mb = os.path.getsize(dest) / (1024 * 1024)
            print(f"[OK] {name} ya existe ({size_mb:.1f} MB): {dest}")
            continue

        print(f"[DESCARGANDO] {name} -> {dest}")
        success = False
        for url in item["urls"]:
            try:
                print(f"  Intentando desde: {url}")
                _download_file(url, dest)
                if os.path.isfile(dest) and os.path.getsize(dest) >= min_bytes:
                    size_mb = os.path.getsize(dest) / (1024 * 1024)
                    print(f"[OK] Descargado {name} ({size_mb:.1f} MB)")
                    success = True
                    break
            except Exception as exc:
                print(f"\n  [WARN] Falló descarga desde {url}: {exc}")

        if not success:
            print(f"[ERROR] No se pudo descargar automáticamente {name}. Colócalo manualmente en {dest}")


if __name__ == "__main__":
    ensure_models()

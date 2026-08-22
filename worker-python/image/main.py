import base64
import io
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from faceswap import FaceSwapRequest, swap_faces
from upscale import upscale_to_fullhd

# Modelo de alta calidad (no-turbo) para fotorrealismo, incluye personas.
# Requiere más pasos de inferencia (mucho más lento que SD-Turbo) pero da resultados
# muchísimo mejores en anatomía, rostros y detalle. Cambiar por env var si se prefiere otro.
MODEL_ID = os.environ.get("GENERATIVA_IMAGE_MODEL_ID", "SG161222/Realistic_Vision_V5.1_noVAE")
MODEL_CACHE_NAME = MODEL_ID.split("/")[-1]
OV_MODEL_DIR = os.environ.get(
    "GENERATIVA_IMAGE_OV_DIR", os.path.join(os.path.dirname(__file__), "ov-models", MODEL_CACHE_NAME)
)
DEVICE = os.environ.get("GENERATIVA_IMAGE_DEVICE", "CPU")  # CPU, GPU (iGPU Intel) o AUTO

_pipe = None
_img2img_pipe = None


def _load_pipeline():
    from optimum.intel import OVStableDiffusionPipeline
    from diffusers import DPMSolverMultistepScheduler

    if os.path.isdir(OV_MODEL_DIR) and os.path.isfile(os.path.join(OV_MODEL_DIR, "model_index.json")):
        print(f"[image-worker] Cargando modelo OpenVINO ya convertido desde {OV_MODEL_DIR}")
        pipe = OVStableDiffusionPipeline.from_pretrained(OV_MODEL_DIR, device=DEVICE)
    else:
        print(f"[image-worker] Convirtiendo {MODEL_ID} a OpenVINO IR (solo la primera vez, puede tardar varios minutos)")
        pipe = OVStableDiffusionPipeline.from_pretrained(MODEL_ID, export=True, device=DEVICE)
        os.makedirs(OV_MODEL_DIR, exist_ok=True)
        pipe.save_pretrained(OV_MODEL_DIR)
        print(f"[image-worker] Modelo convertido y cacheado en {OV_MODEL_DIR}")

    # DPM++ converge a mejor calidad con menos pasos que el scheduler por defecto.
    # Se fuerzan algorithm_type/final_sigmas_type porque algunos checkpoints traen
    # combinaciones (ej. deis + final_sigmas_type=zero) incompatibles con DPM++.
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
        pipe.scheduler.config,
        algorithm_type="dpmsolver++",
        final_sigmas_type="sigma_min",
    )
    return pipe


def _load_img2img_pipeline():
    from optimum.intel import OVStableDiffusionImg2ImgPipeline
    from diffusers import DPMSolverMultistepScheduler

    print("[image-worker] Cargando pipeline de edición (img2img)...")
    pipe = OVStableDiffusionImg2ImgPipeline.from_pretrained(OV_MODEL_DIR, device=DEVICE)
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
        pipe.scheduler.config,
        algorithm_type="dpmsolver++",
        final_sigmas_type="sigma_min",
    )
    print("[image-worker] Pipeline de edición listo")
    return pipe


def _resize_for_sd(image, max_side: int = 768):
    """Reduce/ajusta una imagen al tamaño máximo del modelo, redondeando a múltiplos de 8
    (requerido por el VAE de Stable Diffusion) y preservando la relación de aspecto."""
    width, height = image.size
    scale = max_side / max(width, height)
    new_width = max(8, int(round(width * scale / 8)) * 8)
    new_height = max(8, int(round(height * scale / 8)) * 8)
    return image.resize((new_width, new_height))


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _pipe
    print(f"[image-worker] Inicializando pipeline (device={DEVICE})...")
    _pipe = _load_pipeline()
    print("[image-worker] Pipeline listo")
    yield


app = FastAPI(title="Generativa Image Worker", lifespan=lifespan)


# Reforzado tras pruebas: además de anatomía/calidad, evita que se cuele el look
# "amateur/foto de celular" o que derive a ilustración/render en vez de fotografía.
DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low quality, low resolution, deformed, disfigured, bad anatomy, "
    "extra limbs, extra fingers, missing fingers, fused fingers, too many fingers, "
    "malformed hands, mutated hands, poorly drawn hands, watermark, text, jpeg artifacts, "
    "amateur, snapshot, phone photo, harsh flash, grainy, noisy, out of focus, "
    "flat lighting, underexposed, overexposed, illustration, painting, cartoon, "
    "3d render, cgi, anime, duplicate"
)

# Se añade automáticamente al final de cualquier prompt para subir el nivel base de
# calidad ("máxima calidad posible" sin que el usuario tenga que escribirlo cada vez).
QUALITY_SUFFIX = (
    ", professional photography, ultra detailed, sharp focus, high quality, "
    "8k uhd, natural lighting"
)


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    steps: int = 50
    guidance_scale: float = 7.5
    width: int = 512
    height: int = 768
    seed: Optional[int] = None
    upscale: bool = True


class EditRequest(BaseModel):
    image_base64: str
    prompt: str
    negative_prompt: Optional[str] = None
    strength: float = 0.6
    steps: int = 50
    guidance_scale: float = 7.5
    seed: Optional[int] = None
    upscale: bool = True


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _pipe is not None, "device": DEVICE}


@app.post("/generate")
def generate(req: GenerateRequest):
    if _pipe is None:
        raise HTTPException(status_code=503, detail="El pipeline de imagen no está listo todavía.")

    generator = None
    if req.seed is not None:
        import numpy as np

        generator = np.random.RandomState(req.seed)

    result = _pipe(
        prompt=req.prompt + QUALITY_SUFFIX,
        negative_prompt=req.negative_prompt or DEFAULT_NEGATIVE_PROMPT,
        num_inference_steps=req.steps,
        guidance_scale=req.guidance_scale,
        width=req.width,
        height=req.height,
        generator=generator,
    )
    image = result.images[0]
    if req.upscale:
        image = upscale_to_fullhd(image)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return {"image_base64": image_base64, "format": "png", "width": image.width, "height": image.height}


@app.post("/edit")
def edit(req: EditRequest):
    global _img2img_pipe
    if _pipe is None:
        raise HTTPException(status_code=503, detail="El pipeline de imagen no está listo todavía.")
    if _img2img_pipe is None:
        _img2img_pipe = _load_img2img_pipeline()

    from PIL import Image

    try:
        input_bytes = base64.b64decode(req.image_base64)
        input_image = Image.open(io.BytesIO(input_bytes)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer la imagen: {exc}")

    input_image = _resize_for_sd(input_image)

    generator = None
    if req.seed is not None:
        import numpy as np

        generator = np.random.RandomState(req.seed)

    result = _img2img_pipe(
        prompt=req.prompt + QUALITY_SUFFIX,
        negative_prompt=req.negative_prompt or DEFAULT_NEGATIVE_PROMPT,
        image=input_image,
        strength=req.strength,
        num_inference_steps=req.steps,
        guidance_scale=req.guidance_scale,
        generator=generator,
    )
    image = result.images[0]
    if req.upscale:
        image = upscale_to_fullhd(image)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return {"image_base64": image_base64, "format": "png", "width": image.width, "height": image.height}


@app.post("/faceswap")
def faceswap(req: FaceSwapRequest):
    return swap_faces(req)


class UpscaleRequest(BaseModel):
    image_base64: str


@app.post("/upscale")
def upscale(req: UpscaleRequest):
    from PIL import Image

    try:
        input_bytes = base64.b64decode(req.image_base64)
        input_image = Image.open(io.BytesIO(input_bytes)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer la imagen: {exc}")

    result_image = upscale_to_fullhd(input_image)

    buffer = io.BytesIO()
    result_image.save(buffer, format="PNG")
    image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return {"image_base64": image_base64, "format": "png", "width": result_image.width, "height": result_image.height}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8002)

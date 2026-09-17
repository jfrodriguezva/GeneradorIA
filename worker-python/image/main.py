import base64
import io
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from faceswap import FaceSwapRequest, swap_faces, restore_faces_in_image
from upscale import upscale_to_fullhd
import segmentation
import controlnet as controlnet_mod

# Modelo de alta calidad (no-turbo) para fotorrealismo, incluye personas.
# Requiere más pasos de inferencia (mucho más lento que SD-Turbo) pero da resultados
# muchísimo mejores en anatomía, rostros y detalle. Cambiar por env var si se prefiere otro.
#
# epiCRealism en vez de Realistic Vision (usado hasta antes de este cambio): probado en
# esta sesión con el mismo prompt genérico — rostro notablemente más realista (ojos con
# asimetría/reflejo natural en vez de "mirada vidriosa", piel con textura en vez de
# aerografiada). Fue el cambio de mayor impacto en calidad facial de toda la sesión, más
# que cualquier ajuste de prompt/negative prompt. Mismo tamaño/arquitectura SD1.5, no
# requiere más hardware.
MODEL_ID = os.environ.get("GENERATIVA_IMAGE_MODEL_ID", "emilianJR/epiCRealism")
MODEL_CACHE_NAME = MODEL_ID.split("/")[-1]
OV_MODEL_DIR = os.environ.get(
    "GENERATIVA_IMAGE_OV_DIR", os.path.join(os.path.dirname(__file__), "ov-models", MODEL_CACHE_NAME)
)
DEVICE = os.environ.get("GENERATIVA_IMAGE_DEVICE", "CPU")  # CPU, GPU (iGPU Intel) o AUTO

_pipe = None
_img2img_pipe = None
_inpaint_pipe = None
_controlnet_pipes: dict = {}  # control_type -> pipeline, se cargan bajo demanda
_ipadapter_pipe = None  # pipeline aparte en torch/CPU puro, ver _load_ipadapter_pipeline


def _disable_safety_checker(pipe):
    """Fuerza el safety_checker a None sin importar si el checkpoint lo trae activo.

    Detectado en esta sesión al cambiar a epiCRealism: Realistic Vision (el checkpoint
    anterior) no incluye safety_checker en su config, así que nunca se activaba; epiCRealism
    sí lo trae, y disparó un falso positivo devolviendo una imagen negra en un caso de uso
    normal (inpainting de ropa sobre una foto ya generada). El proyecto no tiene filtro de
    contenido por diseño (ver CLAUDE.md) — esto no debe depender de qué checkpoint se use.
    """
    if hasattr(pipe, "safety_checker"):
        pipe.safety_checker = None
    if hasattr(pipe, "requires_safety_checker"):
        pipe.requires_safety_checker = False
    return pipe


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
    return _disable_safety_checker(pipe)


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
    return _disable_safety_checker(pipe)


def _apply_hires_fix(
    img2img_pipe,
    image,
    prompt: str,
    negative_prompt: str,
    guidance_scale: float,
    generator,
    scale: float = 1.5,
    strength: float = 0.25,
    steps: int = 25,
):
    """Segunda pasada de refinamiento ("hires fix"): reescala la imagen ya generada y la
    vuelve a pasar por img2img con strength moderado. Es la técnica estándar (la misma
    que usan Automatic1111/ComfyUI) para sacarle más detalle fino (textura de tela, piel,
    cabello) a un modelo de baja resolución nativa como SD1.5 sin cambiar la composición
    — a diferencia de simplemente pedir más pasos en la generación original, que no
    añade detalle nuevo, solo refina el mismo nivel de ruido inicial.

    strength bajo a propósito (0.25, no el 0.4 típico de las guías genéricas): en pruebas
    reales, 0.4 le dio suficiente libertad al img2img para desviarse de la composición
    pedida en el prompt (en un caso, un escote que debía quedar cerrado terminó abierto).
    A 0.25 el refinamiento sigue añadiendo nitidez/textura pero se apega más a la imagen
    de entrada. No se agregó ningún término de negative_prompt para esto a propósito: el
    proyecto no tiene filtro de contenido por diseño (ver CLAUDE.md) y este es un ajuste
    de fidelidad a la composición pedida, no una decisión de qué contenido permitir.
    """
    upscaled = image.resize((round(image.width * scale), round(image.height * scale)))
    upscaled = _resize_for_sd(upscaled, max_side=max(upscaled.size))

    result = img2img_pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=upscaled,
        strength=strength,
        num_inference_steps=steps,
        guidance_scale=guidance_scale,
        generator=generator,
    )
    return result.images[0]


def _load_inpaint_pipeline():
    from optimum.intel import OVStableDiffusionInpaintPipeline
    from diffusers import DPMSolverMultistepScheduler

    # Reutiliza el mismo checkpoint (Realistic Vision) que txt2img/img2img: no es un
    # checkpoint "inpainting-specific" (9 canales), así que optimum-intel lo corre en
    # modo "legacy" (mezcla latentes según la máscara en cada paso). Funciona bien para
    # ediciones localizadas con strength alto (0.8-0.95) en la zona enmascarada.
    print("[image-worker] Cargando pipeline de inpainting...")
    pipe = OVStableDiffusionInpaintPipeline.from_pretrained(OV_MODEL_DIR, device=DEVICE)
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
        pipe.scheduler.config,
        algorithm_type="dpmsolver++",
        final_sigmas_type="sigma_min",
    )
    print("[image-worker] Pipeline de inpainting listo")
    return _disable_safety_checker(pipe)


def _load_controlnet_pipeline(control_type: str):
    # Verificado en desarrollo: optimum-intel 1.22.0 (la versión que usa este proyecto)
    # NO expone OVStableDiffusionControlNetPipeline/OVControlNetModel para SD1.5 (ese
    # soporte solo existe ahí para SD3/SDXL) — así que, igual que IP-Adapter, este
    # pipeline usa diffusers "puro" en torch CPU en vez de OpenVINO. Es más lento que
    # /generate o /edit; si optimum-intel agrega soporte ControlNet para SD1.5 en el
    # futuro, migrar esto para recuperar la aceleración.
    import torch
    from diffusers import StableDiffusionControlNetPipeline, ControlNetModel, DPMSolverMultistepScheduler

    if control_type in _controlnet_pipes:
        return _controlnet_pipes[control_type]

    model_id = controlnet_mod.CONTROLNET_MODEL_IDS[control_type]
    print(f"[image-worker] Cargando ControlNet ({control_type}) desde {model_id} (torch CPU)...")
    controlnet = ControlNetModel.from_pretrained(model_id, torch_dtype=torch.float32)
    pipe = StableDiffusionControlNetPipeline.from_pretrained(
        MODEL_ID, controlnet=controlnet, torch_dtype=torch.float32, safety_checker=None
    )
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
        pipe.scheduler.config,
        algorithm_type="dpmsolver++",
        final_sigmas_type="sigma_min",
    )
    print(f"[image-worker] ControlNet ({control_type}) listo")
    _controlnet_pipes[control_type] = pipe
    return pipe


def _load_ipadapter_pipeline():
    # IP-Adapter (condicionar la generación con una foto de referencia para mantener la
    # identidad de una persona en escenas nuevas) no tiene soporte estable en
    # optimum-intel/OpenVINO para SD1.5 al momento de escribir esto — por eso este
    # pipeline usa diffusers "puro" en torch CPU en vez del resto (que sí va por
    # OpenVINO). Es más lento que los otros endpoints; si en el futuro optimum-intel
    # soporta IP-Adapter con export=True, migrar esto para recuperar la velocidad.
    import torch
    from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler

    print("[image-worker] Cargando pipeline IP-Adapter (torch CPU, sin aceleración OpenVINO)...")
    pipe = StableDiffusionPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.float32, safety_checker=None)
    pipe.load_ip_adapter(
        "h94/IP-Adapter", subfolder="models", weight_name="ip-adapter-full-face_sd15.bin"
    )
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
        pipe.scheduler.config,
        algorithm_type="dpmsolver++",
        final_sigmas_type="sigma_min",
    )
    print("[image-worker] Pipeline IP-Adapter listo")
    return pipe


def _mask_bbox_with_padding(mask_image, width: int, height: int, padding_ratio: float):
    bbox = mask_image.point(lambda p: 255 if p > 10 else 0).getbbox()
    if bbox is None:
        return (0, 0, width, height)
    x0, y0, x1, y1 = bbox
    pad_x = int((x1 - x0) * padding_ratio)
    pad_y = int((y1 - y0) * padding_ratio)
    x0 = max(0, x0 - pad_x)
    y0 = max(0, y0 - pad_y)
    x1 = min(width, x1 + pad_x)
    y1 = min(height, y1 + pad_y)
    return (x0, y0, x1, y1)


def _apply_hires_fix_to_masked_region(
    img2img_pipe,
    image,
    mask_image,
    prompt: str,
    negative_prompt: str,
    guidance_scale: float,
    generator,
    padding_ratio: float = 0.12,
    **hires_kwargs,
):
    """Igual que _apply_hires_fix, pero solo dentro de la zona de la máscara (mismo
    recorte que usó /inpaint). Hace falta esta variante para /inpaint: aplicar el
    refinamiento sobre la imagen COMPLETA (como hacen /generate y /edit, que no tienen
    concepto de "zona editada") deja que el img2img sin restricción reinterprete partes
    de la foto fuera de lo que se pidió cambiar — se detectó esto en pruebas reales,
    donde afectó incluso el escote de la prenda más allá de lo generado por el inpaint.
    Restringir el refinamiento al mismo recorte evita ese arrastre."""
    from PIL import Image, ImageFilter

    width, height = image.size
    x0, y0, x1, y1 = _mask_bbox_with_padding(mask_image, width, height, padding_ratio)

    crop = image.crop((x0, y0, x1, y1))
    mask_crop = mask_image.crop((x0, y0, x1, y1))

    refined_crop = _apply_hires_fix(
        img2img_pipe, crop, prompt=prompt, negative_prompt=negative_prompt,
        guidance_scale=guidance_scale, generator=generator, **hires_kwargs,
    ).resize(crop.size)

    mask_blend = mask_crop.filter(ImageFilter.GaussianBlur(radius=6))
    blended_crop = Image.composite(refined_crop, crop, mask_blend)

    output = image.copy()
    output.paste(blended_crop, (x0, y0))
    return output


def _run_inpaint_cropped(
    pipe,
    image,
    mask_image,
    prompt: str,
    negative_prompt: str,
    strength: float,
    steps: int,
    guidance_scale: float,
    generator,
    crop_max_side: int = 768,  # subido de 640: más resolución para detalle fino de tela/costuras
    padding_ratio: float = 0.25,
):
    """Corre el inpainting solo en la zona de la máscara (con margen), a resolución
    completa del modelo, y la vuelve a pegar en la imagen original con blending.

    Correr el inpainting sobre la imagen completa (como se hacía antes) reparte la
    "atención" del modelo sobre toda la foto y, en modo legacy (checkpoint no
    inpainting-specific), termina regenerando un poco el fondo/zonas fuera de la
    máscara a baja intensidad — eso es lo que se veía como un artefacto de "doble
    exposición"/fantasma cerca de los bordes. Recortar primero (la técnica estándar de
    "inpaint solo lo enmascarado" que usan Automatic1111/ComfyUI) evita ese problema:
    el modelo dedica toda su resolución a la prenda/zona editada y el resto de la foto
    queda intocado en píxeles.
    """
    from PIL import Image, ImageFilter

    width, height = image.size
    x0, y0, x1, y1 = _mask_bbox_with_padding(mask_image, width, height, padding_ratio)

    crop = image.crop((x0, y0, x1, y1))
    mask_crop = mask_image.crop((x0, y0, x1, y1))
    crop_size = crop.size

    crop_resized = _resize_for_sd(crop, max_side=crop_max_side)
    mask_resized = mask_crop.resize(crop_resized.size)

    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=crop_resized,
        mask_image=mask_resized,
        strength=strength,
        num_inference_steps=steps,
        guidance_scale=guidance_scale,
        generator=generator,
    )
    generated_crop = result.images[0].resize(crop_size)

    # Blend con la máscara original. Se difumina un poco más de lo que ya trae
    # (segmentation.generate_mask aplica su propio feather, o el usuario mandó una a
    # mano) porque el redimensionado de ida y vuelta (crop -> resolución del modelo ->
    # tamaño original) puede desalinear el borde por sub-píxel contra la máscara nativa,
    # lo que se notaba como una costura/halo tenue en el borde del parche.
    mask_blend = mask_crop.filter(ImageFilter.GaussianBlur(radius=6))
    blended_crop = Image.composite(generated_crop, crop, mask_blend)

    output = image.copy()
    output.paste(blended_crop, (x0, y0))
    return output


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
# "duplicate limbs/double exposure/ghosting" se agregó tras detectar ese artefacto
# específico en pruebas de /inpaint — ayuda en cualquier endpoint, no solo ahí.
DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low quality, low resolution, deformed, disfigured, bad anatomy, "
    "extra limbs, extra fingers, missing fingers, fused fingers, too many fingers, "
    "malformed hands, mutated hands, poorly drawn hands, watermark, text, jpeg artifacts, "
    "amateur, snapshot, phone photo, harsh flash, grainy, noisy, out of focus, "
    "flat lighting, underexposed, overexposed, illustration, painting, cartoon, "
    "3d render, cgi, anime, duplicate, duplicate limbs, extra arm, double exposure, ghosting, "
    # Agregado tras notar que las caras salían con un look sintético/plástico
    # reconocible: simetría perfecta, mirada vidriosa/vacía y piel demasiado uniforme
    # son justo los tells clásicos de SD1.5 que un negative prompt sí puede atenuar
    # (no elimina el techo del modelo, pero ayuda). No probado A/B en esta sesión.
    "perfectly symmetrical face, doll-like eyes, glassy eyes, vacant stare, dead eyes, "
    "airbrushed skin, plastic skin, waxy skin, mannequin, uncanny valley, "
    # Proporciones corporales: "bad anatomy" ya estaba pero es muy genérico. Estos son
    # los errores de proporción específicos y recurrentes de SD1.5 (torso/cuello
    # alargados, cabeza chica, brazos cortos) — no probado A/B en esta sesión.
    "long torso, elongated neck, small head, disproportionate body, "
    "long body, short arms, malformed body proportions, "
    # Detectado repetidamente en /inpaint con prendas de tirantes finos: el modelo
    # intenta agregar una capa/chal translúcido que no resuelve bien (se ve como un
    # "fantasma" en los hombros) y el color pedido se diluye hacia tonos pastel. Probado
    # en aislamiento (misma semilla, mismo padding, solo este cambio): sí corrige el
    # color de forma consistente; el fantasma se reduce pero no se elimina del todo —
    # sigue siendo el punto débil conocido de este tipo de prenda en este pipeline.
    "sheer overlay, cape, shawl, wrap, sheer cape sleeves, translucent fabric drape, "
    "floating fabric, disconnected fabric, extra limb, floating limb, disembodied limb, "
    "wrong color, faded color, desaturated color"
)

# Se añade automáticamente al final de cualquier prompt para subir el nivel base de
# calidad ("máxima calidad posible" sin que el usuario tenga que escribirlo cada vez).
# Se cambió la iluminación de "three-point studio lighting, softbox" (muy plana/pareja,
# uno de los tells de que la cara "se ve falsa") a luz direccional suave.
#
# OJO — probado en esta sesión y revertido en parte: una primera versión usaba "soft
# directional window light" + "candid editorial photoshoot". Con un prompt genérico sin
# describir ropa, esa combinación derivó en desnudez no pedida — probablemente porque
# esos términos están asociados en el dataset de este checkpoint (Realistic Vision) con
# fotografía íntima/boudoir. Se quitaron "window light" y "candid" por esa razón, dejando
# solo iluminación de estudio direccional (menos plana que el "three-point" original,
# sin el vocabulario asociado a boudoir). Esta versión revertida NO se volvió a correr
# de punta a punta tras el cambio — si generas algo con esto, revisa el resultado.
QUALITY_SUFFIX = (
    ", professional photography, shot on Canon EOS R5, 85mm lens, "
    "softbox key light with subtle rim light, gentle directional shadows, "
    "ultra detailed, sharp focus, high quality, 8k uhd, natural skin texture, "
    "subtle skin imperfections, editorial photoshoot"
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
    # Segunda pasada de refinamiento (ver _apply_hires_fix): mejora nitidez/detalle de
    # tela y piel a costa de ~30-40% más tiempo. Apagado por default porque no es gratis.
    hires_fix: bool = False
    # GFPGAN sobre el resultado (no solo en face-swap). Requiere GFPGANv1.4.pth; si no
    # está, se ignora sin error (igual que en /faceswap).
    restore_faces: bool = False


class EditRequest(BaseModel):
    image_base64: str
    prompt: str
    negative_prompt: Optional[str] = None
    strength: float = 0.6
    steps: int = 50
    guidance_scale: float = 7.5
    seed: Optional[int] = None
    hires_fix: bool = False
    restore_faces: bool = False
    upscale: bool = True


class InpaintRequest(BaseModel):
    image_base64: str
    prompt: str
    negative_prompt: Optional[str] = None
    # Una de las dos: mask_base64 (dibujada/provista por el usuario, blanco = editar) o
    # mask_target (segmentación automática: "ropa", "fondo", "persona", "rostro").
    mask_base64: Optional[str] = None
    mask_target: Optional[str] = None
    # Ahora que /inpaint recorta y regenera solo la zona enmascarada (ver
    # _run_inpaint_cropped), conviene un strength alto por default: ya no "arrastra" el
    # resto de la foto como pasaba corriéndolo sobre la imagen completa.
    strength: float = 0.97
    steps: int = 50
    guidance_scale: float = 7.5
    seed: Optional[int] = None
    upscale: bool = True
    hires_fix: bool = False
    restore_faces: bool = False


class ControlledGenerateRequest(BaseModel):
    reference_image_base64: str  # foto de la que se extrae la pose/bordes a conservar
    control_type: str = "pose"  # "pose" | "edges"
    prompt: str
    negative_prompt: Optional[str] = None
    controlnet_conditioning_scale: float = 1.0
    steps: int = 50
    guidance_scale: float = 7.5
    seed: Optional[int] = None
    upscale: bool = True


class ReferenceGenerateRequest(BaseModel):
    reference_image_base64: str  # foto de la persona cuya identidad se quiere mantener
    prompt: str
    negative_prompt: Optional[str] = None
    ip_adapter_scale: float = 0.6
    steps: int = 30
    guidance_scale: float = 7.5
    width: int = 512
    height: int = 768
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

    if req.hires_fix:
        global _img2img_pipe
        if _img2img_pipe is None:
            _img2img_pipe = _load_img2img_pipeline()
        image = _apply_hires_fix(
            _img2img_pipe,
            image,
            prompt=req.prompt + QUALITY_SUFFIX,
            negative_prompt=req.negative_prompt or DEFAULT_NEGATIVE_PROMPT,
            guidance_scale=req.guidance_scale,
            generator=generator,
        )

    if req.restore_faces:
        image, _ = restore_faces_in_image(image)

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

    if req.hires_fix:
        image = _apply_hires_fix(
            _img2img_pipe,
            image,
            prompt=req.prompt + QUALITY_SUFFIX,
            negative_prompt=req.negative_prompt or DEFAULT_NEGATIVE_PROMPT,
            guidance_scale=req.guidance_scale,
            generator=generator,
        )

    if req.restore_faces:
        image, _ = restore_faces_in_image(image)

    if req.upscale:
        image = upscale_to_fullhd(image)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return {"image_base64": image_base64, "format": "png", "width": image.width, "height": image.height}


@app.post("/inpaint")
def inpaint(req: InpaintRequest):
    """Edita solo una zona de la imagen (ropa, fondo, persona completa o rostro) dejando
    el resto intacto. La máscara se puede pasar a mano (mask_base64) o pedir que se
    genere sola por segmentación (mask_target)."""
    global _inpaint_pipe
    if _pipe is None:
        raise HTTPException(status_code=503, detail="El pipeline de imagen no está listo todavía.")
    if not req.mask_base64 and not req.mask_target:
        raise HTTPException(status_code=400, detail="Falta mask_base64 o mask_target.")
    if _inpaint_pipe is None:
        _inpaint_pipe = _load_inpaint_pipeline()

    from PIL import Image

    try:
        input_bytes = base64.b64decode(req.image_base64)
        input_image = Image.open(io.BytesIO(input_bytes)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer la imagen: {exc}")

    input_image = _resize_for_sd(input_image)

    if req.mask_base64:
        try:
            mask_bytes = base64.b64decode(req.mask_base64)
            mask_image = Image.open(io.BytesIO(mask_bytes)).convert("L").resize(input_image.size)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"No se pudo leer la máscara: {exc}")
    else:
        try:
            mask_image = segmentation.generate_mask(input_image, req.mask_target)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    generator = None
    if req.seed is not None:
        import numpy as np

        generator = np.random.RandomState(req.seed)

    image = _run_inpaint_cropped(
        _inpaint_pipe,
        input_image,
        mask_image,
        prompt=req.prompt + QUALITY_SUFFIX,
        negative_prompt=req.negative_prompt or DEFAULT_NEGATIVE_PROMPT,
        strength=req.strength,
        steps=req.steps,
        guidance_scale=req.guidance_scale,
        generator=generator,
    )

    if req.hires_fix:
        # Restringido a la misma zona enmascarada (ver _apply_hires_fix_to_masked_region):
        # aplicarlo sin máscara sobre toda la imagen dejó que el refinamiento reinterpretara
        # partes de la foto fuera de lo pedido (detectado en pruebas reales).
        global _img2img_pipe
        if _img2img_pipe is None:
            _img2img_pipe = _load_img2img_pipeline()
        image = _apply_hires_fix_to_masked_region(
            _img2img_pipe,
            image,
            mask_image,
            prompt=req.prompt + QUALITY_SUFFIX,
            negative_prompt=req.negative_prompt or DEFAULT_NEGATIVE_PROMPT,
            guidance_scale=req.guidance_scale,
            generator=generator,
        )

    if req.restore_faces:
        image, _ = restore_faces_in_image(image)

    if req.upscale:
        image = upscale_to_fullhd(image)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return {"image_base64": image_base64, "format": "png", "width": image.width, "height": image.height}


@app.post("/generate-controlled")
def generate_controlled(req: ControlledGenerateRequest):
    """Genera una imagen nueva (escenario/ropa distintos, prompt libre) conservando la
    pose o los contornos exactos de una foto de referencia, vía ControlNet."""
    from PIL import Image

    try:
        ref_bytes = base64.b64decode(req.reference_image_base64)
        reference_image = Image.open(io.BytesIO(ref_bytes)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer la imagen de referencia: {exc}")

    reference_image = _resize_for_sd(reference_image)

    try:
        control_image = controlnet_mod.build_control_image(reference_image, req.control_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    pipe = _load_controlnet_pipeline(req.control_type)

    generator = None
    if req.seed is not None:
        import numpy as np

        generator = np.random.RandomState(req.seed)

    result = pipe(
        prompt=req.prompt + QUALITY_SUFFIX,
        negative_prompt=req.negative_prompt or DEFAULT_NEGATIVE_PROMPT,
        image=control_image,
        controlnet_conditioning_scale=req.controlnet_conditioning_scale,
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


@app.post("/generate-with-reference")
def generate_with_reference(req: ReferenceGenerateRequest):
    """Genera una escena nueva a partir de un prompt manteniendo la identidad/rostro de
    la persona de reference_image_base64 (IP-Adapter). Para "la misma persona en otra
    escena", distinto de face-swap (que pega una cara sobre una foto ya existente)."""
    global _ipadapter_pipe
    if _ipadapter_pipe is None:
        _ipadapter_pipe = _load_ipadapter_pipeline()

    from PIL import Image

    try:
        ref_bytes = base64.b64decode(req.reference_image_base64)
        reference_image = Image.open(io.BytesIO(ref_bytes)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer la imagen de referencia: {exc}")

    _ipadapter_pipe.set_ip_adapter_scale(req.ip_adapter_scale)

    generator = None
    if req.seed is not None:
        import torch

        generator = torch.Generator().manual_seed(req.seed)

    result = _ipadapter_pipe(
        prompt=req.prompt + QUALITY_SUFFIX,
        negative_prompt=req.negative_prompt or DEFAULT_NEGATIVE_PROMPT,
        ip_adapter_image=reference_image,
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

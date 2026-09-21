"""Inpainting con máscara: regenera solo la región marcada y la compone sobre la original.

La diferencia con img2img (`/edit`) es la que decide si el resultado pasa por real: img2img
re-difunde la imagen entera, así que la cara se regenera junto con la ropa y la persona deja
de ser la misma antes incluso de que la prenda cambie. Aquí solo se difunde lo que marca la
máscara y el resto se conserva **píxel a píxel del original, a resolución completa**. La
identidad no se preserva por equilibrio de parámetros: se preserva porque no se toca.

Usa un checkpoint de inpainting propio (SD1.5-inpainting), distinto al de txt2img: su UNet
tiene canales extra para la máscara, y por eso rellena bordes mucho mejor que reutilizar el
modelo normal.
"""

import os

import numpy as np
from PIL import Image

MODEL_ID = os.environ.get(
    "GENERATIVA_INPAINT_MODEL_ID", "stable-diffusion-v1-5/stable-diffusion-inpainting"
)
OV_MODEL_DIR = os.environ.get(
    "GENERATIVA_INPAINT_OV_DIR",
    os.path.join(os.path.dirname(__file__), "ov-models", MODEL_ID.split("/")[-1]),
)
DEVICE = os.environ.get("GENERATIVA_IMAGE_DEVICE", "CPU")

# Lado largo al que se difunde. SD1.5 es nativo de 512; por encima de ~768 empieza a
# duplicar elementos, así que se difunde pequeño y se compone sobre la original grande.
MAX_DIFFUSION_SIDE = int(os.environ.get("GENERATIVA_INPAINT_MAX_SIDE", "768"))

_pipe = None

# Factor de escala del VAE de SD1.5. Tiene que estar en la config guardada del IR.
SD15_VAE_SCALING_FACTOR = 0.18215


def _ensure_vae_scaling_factor(model_dir: str) -> None:
    """Repara la config del VAE si la conversión a IR no guardó `scaling_factor`.

    `save_pretrained` del checkpoint de inpainting no persiste ese valor, y sin él el
    decodificador escala mal los latentes: **todas las imágenes salen en negro**. El fallo
    no se ve al convertir (el pipeline recién exportado conserva el valor en memoria), solo
    al recargar el modelo desde disco, que es lo que pasa en todos los arranques siguientes.
    """
    import json

    for part in ("vae_decoder", "vae_encoder"):
        config_path = os.path.join(model_dir, part, "config.json")
        if not os.path.isfile(config_path):
            continue

        with open(config_path, encoding="utf-8") as handle:
            config = json.load(handle)
        if config.get("scaling_factor") is not None:
            continue

        config["scaling_factor"] = SD15_VAE_SCALING_FACTOR
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2)
        print(f"[inpaint] {part}: se añadió scaling_factor a la config (faltaba tras la conversión)")


def _load_pipeline():
    global _pipe
    if _pipe is not None:
        return _pipe

    from diffusers import DPMSolverMultistepScheduler
    from optimum.intel import OVStableDiffusionInpaintPipeline

    if os.path.isdir(OV_MODEL_DIR) and os.path.isfile(os.path.join(OV_MODEL_DIR, "model_index.json")):
        _ensure_vae_scaling_factor(OV_MODEL_DIR)
        print(f"[inpaint] Cargando modelo OpenVINO ya convertido desde {OV_MODEL_DIR}")
        pipe = OVStableDiffusionInpaintPipeline.from_pretrained(OV_MODEL_DIR, device=DEVICE)
    else:
        print(f"[inpaint] Convirtiendo {MODEL_ID} a OpenVINO IR (solo la primera vez, tarda varios minutos)")
        pipe = OVStableDiffusionInpaintPipeline.from_pretrained(MODEL_ID, export=True, device=DEVICE)
        os.makedirs(OV_MODEL_DIR, exist_ok=True)
        pipe.save_pretrained(OV_MODEL_DIR)
        _ensure_vae_scaling_factor(OV_MODEL_DIR)
        print(f"[inpaint] Modelo convertido y cacheado en {OV_MODEL_DIR}")

    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
        pipe.scheduler.config,
        algorithm_type="dpmsolver++",
        final_sigmas_type="sigma_min",
    )
    _pipe = pipe
    print("[inpaint] Pipeline de inpainting listo")
    return _pipe


def is_loaded() -> bool:
    return _pipe is not None


def _diffusion_size(width: int, height: int) -> tuple[int, int]:
    """Tamaño al que difundir: lado largo <= MAX_DIFFUSION_SIDE y múltiplos de 8."""
    scale = min(1.0, MAX_DIFFUSION_SIDE / max(width, height))
    return (
        max(8, int(round(width * scale / 8)) * 8),
        max(8, int(round(height * scale / 8)) * 8),
    )


def composite(original: Image.Image, generated: Image.Image, mask: Image.Image) -> Image.Image:
    """Funde lo generado sobre la original usando la máscara difuminada como alfa.

    Se hace a la resolución de la original, no a la de difusión: fuera de la máscara el
    resultado es idéntico bit a bit a la foto de partida.
    """
    generated = generated.convert("RGB").resize(original.size, Image.LANCZOS)
    mask = mask.convert("L").resize(original.size, Image.LANCZOS)

    base = np.asarray(original.convert("RGB"), dtype=np.float32)
    new = np.asarray(generated, dtype=np.float32)
    alpha = (np.asarray(mask, dtype=np.float32) / 255.0)[..., None]

    return Image.fromarray(np.clip(base * (1 - alpha) + new * alpha, 0, 255).astype(np.uint8))


def inpaint(
    image: Image.Image,
    mask: Image.Image,
    prompt: str,
    negative_prompt: str | None = None,
    steps: int = 30,
    guidance_scale: float = 7.5,
    seed: int | None = None,
) -> Image.Image:
    """Regenera la zona marcada según el prompt y la compone sobre la imagen original."""
    pipe = _load_pipeline()

    original = image.convert("RGB")
    width, height = _diffusion_size(*original.size)

    generator = None
    if seed is not None:
        generator = np.random.RandomState(seed)

    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=original.resize((width, height), Image.LANCZOS),
        mask_image=mask.convert("L").resize((width, height), Image.LANCZOS),
        width=width,
        height=height,
        num_inference_steps=steps,
        guidance_scale=guidance_scale,
        generator=generator,
    )

    return composite(original, result.images[0], mask)

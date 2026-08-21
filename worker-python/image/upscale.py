"""Escalado de imágenes a Full HD (o más) usando el módulo dnn_superres de OpenCV
(modelo FSRCNN x4). Es mucho más rápido que generar directamente a alta resolución
con el pipeline de difusión, y da mejores resultados que un resize normal."""

import os

import cv2
import numpy as np
from PIL import Image

MODEL_PATH = os.environ.get(
    "GENERATIVA_UPSCALE_MODEL_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "upscale-models", "FSRCNN_x4.pb"),
)

_upscaler = None


def _load_upscaler():
    global _upscaler
    if _upscaler is not None:
        return _upscaler
    if not os.path.isfile(MODEL_PATH):
        raise FileNotFoundError(f"No se encontró el modelo de escalado en {MODEL_PATH}")

    sr = cv2.dnn_superres.DnnSuperResImpl_create()
    sr.readModel(MODEL_PATH)
    sr.setModel("fsrcnn", 4)
    _upscaler = sr
    return sr


def upscale_to_fullhd(image: Image.Image, target_long_side: int = 1920) -> Image.Image:
    """Escala x4 con FSRCNN y luego ajusta al tamaño objetivo (por defecto, que el
    lado largo llegue a 1920px, es decir, calidad Full HD) preservando la relación
    de aspecto original."""
    sr = _load_upscaler()

    bgr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    upscaled_bgr = sr.upsample(bgr)

    height, width = upscaled_bgr.shape[:2]
    long_side = max(width, height)
    if long_side > target_long_side:
        scale = target_long_side / long_side
        new_width = max(1, int(round(width * scale)))
        new_height = max(1, int(round(height * scale)))
        upscaled_bgr = cv2.resize(upscaled_bgr, (new_width, new_height), interpolation=cv2.INTER_AREA)

    upscaled_rgb = cv2.cvtColor(upscaled_bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(upscaled_rgb)

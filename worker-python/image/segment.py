"""Segmentación de ropa para inpainting: marca qué píxeles son prenda y cuáles no.

Es la pieza que hace posible cambiar la ropa sin perder a la persona. Con img2img se
re-difunde la imagen entera, así que la cara pasa por el modelo igual que la ropa y la
identidad se pierde antes incluso de que la prenda llegue a cambiar. Aquí se genera una
máscara para difundir *solo* la región de ropa: la cara, el pelo y el fondo se quedan
como píxeles del original.

Usa SegFormer (mattmdjaga/segformer_b2_clothes), ~100MB, segundos en CPU.
"""

import os

import cv2
import numpy as np
from PIL import Image

MODEL_ID = os.environ.get("GENERATIVA_SEGMENT_MODEL_ID", "mattmdjaga/segformer_b2_clothes")
MODELS_ROOT = os.environ.get(
    "GENERATIVA_SEGMENT_MODELS_ROOT",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "segmentation-models"),
)

# Etiquetas del modelo (esquema ATR). Se listan todas aunque solo se usen las de ropa:
# saber qué es cara/pelo/brazo es lo que permite excluirlos de la máscara.
LABELS = {
    0: "background", 1: "hat", 2: "hair", 3: "sunglasses", 4: "upper-clothes",
    5: "skirt", 6: "pants", 7: "dress", 8: "belt", 9: "left-shoe", 10: "right-shoe",
    11: "face", 12: "left-leg", 13: "right-leg", 14: "left-arm", 15: "right-arm",
    16: "bag", 17: "scarf",
}

# Lo que se reemplaza por defecto al pedir "cámbiale la ropa": prendas, nada de piel.
DEFAULT_GARMENT_LABELS = ("upper-clothes", "skirt", "pants", "dress", "belt", "scarf")

_processor = None
_model = None


def _load_model():
    global _processor, _model
    if _model is not None:
        return _processor, _model

    from transformers import AutoModelForSemanticSegmentation, SegformerImageProcessor

    print(f"[segment] Cargando modelo de segmentación de ropa ({MODEL_ID})...")
    os.makedirs(MODELS_ROOT, exist_ok=True)
    _processor = SegformerImageProcessor.from_pretrained(MODEL_ID, cache_dir=MODELS_ROOT)
    _model = AutoModelForSemanticSegmentation.from_pretrained(MODEL_ID, cache_dir=MODELS_ROOT)
    _model.eval()
    print("[segment] Modelo de segmentación listo")
    return _processor, _model


def label_map(image: Image.Image) -> np.ndarray:
    """Devuelve un array HxW donde cada píxel es el id de etiqueta (ver LABELS)."""
    import torch

    processor, model = _load_model()
    inputs = processor(images=image.convert("RGB"), return_tensors="pt")

    with torch.no_grad():
        logits = model(**inputs).logits

    # El modelo trabaja a menor resolución: se reescala a la de la imagen original.
    upsampled = torch.nn.functional.interpolate(
        logits, size=image.size[::-1], mode="bilinear", align_corners=False
    )
    return upsampled.argmax(dim=1)[0].numpy().astype(np.uint8)


def clothing_mask(
    image: Image.Image,
    labels: tuple[str, ...] = DEFAULT_GARMENT_LABELS,
    dilate_px: int = 12,
    feather_px: int = 9,
) -> Image.Image:
    """Máscara en blanco (lo que se regenera) y negro (lo que se conserva).

    Se dilata y se difumina el borde a propósito: una máscara pegada al contorno exacto
    de la prenda deja una costura dura y visible entre lo generado y lo original, que es
    justo el detalle que delata un montaje.
    """
    ids = label_map(image)
    wanted = [i for i, name in LABELS.items() if name in labels]
    mask = np.isin(ids, wanted).astype(np.uint8) * 255

    if dilate_px > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px * 2 + 1,) * 2)
        mask = cv2.dilate(mask, kernel)

    if feather_px > 0:
        blur = feather_px * 2 + 1
        mask = cv2.GaussianBlur(mask, (blur, blur), 0)

    return Image.fromarray(mask, mode="L")


def coverage(mask: Image.Image) -> float:
    """Fracción de la imagen que cubre la máscara (para avisar si algo salió mal)."""
    arr = np.asarray(mask, dtype=np.float32) / 255.0
    return float(arr.mean())

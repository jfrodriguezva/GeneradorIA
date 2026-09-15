"""Segmentación automática de persona/ropa/rostro para generar máscaras de inpainting
sin que el usuario tenga que dibujarlas a mano.

Usa SegFormer (`mattmdjaga/segformer_b2_clothes`, vía transformers) — ya viene en las
dependencias del proyecto (transformers), no añade un runtime nuevo. Corre en CPU en
~1-2s, mucho más rápido que la propia difusión así que no es el cuello de botella.
"""

import numpy as np
from PIL import Image, ImageFilter

SEGFORMER_MODEL_ID = "mattmdjaga/segformer_b2_clothes"

# Etiquetas del modelo (17 clases + fondo). Se agrupan en "targets" con sentido para el
# usuario en vez de exponer los índices crudos.
LABELS = {
    0: "background", 1: "hat", 2: "hair", 3: "sunglasses", 4: "upper_clothes",
    5: "skirt", 6: "pants", 7: "dress", 8: "belt", 9: "left_shoe", 10: "right_shoe",
    11: "face", 12: "left_leg", 13: "right_leg", 14: "left_arm", 15: "right_arm",
    16: "bag", 17: "scarf",
}
_NAME_TO_ID = {name: idx for idx, name in LABELS.items()}

# "ropa": todo lo que es prenda de vestir (para "cámbiale la ropa a esta persona").
# "fondo": el fondo (para "cámbiale el escenario/fondo" dejando a la persona intacta).
# "persona": todo menos el fondo (para reemplazar completamente el sujeto).
# "rostro": cara + cabello (para ediciones dirigidas al rostro que no sean face-swap).
TARGET_GROUPS = {
    "ropa": ["upper_clothes", "skirt", "pants", "dress", "belt", "scarf"],
    "fondo": ["background"],
    "persona": [name for name in _NAME_TO_ID if name != "background"],
    "rostro": ["face", "hair"],
}

_processor = None
_model = None


def _load_model():
    global _processor, _model
    if _model is not None:
        return
    from transformers import AutoModelForSemanticSegmentation, SegformerImageProcessor

    print(f"[segmentation] Cargando modelo de segmentación ({SEGFORMER_MODEL_ID})...")
    _processor = SegformerImageProcessor.from_pretrained(SEGFORMER_MODEL_ID)
    _model = AutoModelForSemanticSegmentation.from_pretrained(SEGFORMER_MODEL_ID)
    _model.eval()
    print("[segmentation] Modelo de segmentación listo")


def generate_mask(image: Image.Image, target: str, feather: int = 8, dilate: int = 6) -> Image.Image:
    """Devuelve una máscara L (blanco = zona a editar) para el `target` pedido.

    `dilate` agranda un poco la zona seleccionada (para no dejar un borde visible de la
    prenda/fondo original) y `feather` difumina el borde para que el inpainting mezcle
    mejor con el resto de la imagen.
    """
    if target not in TARGET_GROUPS:
        raise ValueError(f"target desconocido: {target}. Opciones: {list(TARGET_GROUPS)}")

    _load_model()

    import torch

    inputs = _processor(images=image, return_tensors="pt")
    with torch.no_grad():
        outputs = _model(**inputs)
    logits = outputs.logits  # (1, num_labels, H, W) a resolución reducida
    upsampled = torch.nn.functional.interpolate(
        logits, size=image.size[::-1], mode="bilinear", align_corners=False
    )
    seg = upsampled.argmax(dim=1)[0].numpy()  # (H, W) con el id de clase por pixel

    target_ids = {_NAME_TO_ID[name] for name in TARGET_GROUPS[target]}
    mask_arr = np.isin(seg, list(target_ids)).astype(np.uint8) * 255
    mask = Image.fromarray(mask_arr, mode="L")

    if dilate > 0:
        mask = mask.filter(ImageFilter.MaxFilter(size=dilate * 2 + 1))
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=feather))

    return mask

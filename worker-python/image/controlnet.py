"""Preprocesadores de ControlNet: extraen de una foto de referencia la estructura
(bordes o esqueleto/pose) que se le va a "imponer" a la generación, para poder cambiar
ropa/escenario **conservando la pose y proporciones exactas** de la persona original.

- "edges" (Canny, solo OpenCV, sin modelo adicional): rápido, bueno para conservar
  contornos/objetos en general.
- "pose" (OpenPose vía controlnet_aux): más lento (descarga su propio modelo pequeño la
  primera vez) pero es lo indicado para preservar la postura de una persona sin arrastrar
  su ropa/fondo actuales, que es justo lo que se necesita para "cambia el escenario/ropa
  pero deja la pose igual".
"""

import cv2
import numpy as np
from PIL import Image

_openpose_detector = None


def _load_openpose():
    global _openpose_detector
    if _openpose_detector is not None:
        return _openpose_detector
    from controlnet_aux import OpenposeDetector

    print("[controlnet] Cargando detector de pose (OpenPose, primera vez descarga el modelo)...")
    _openpose_detector = OpenposeDetector.from_pretrained("lllyasviel/ControlNet")
    print("[controlnet] Detector de pose listo")
    return _openpose_detector


def extract_edges(image: Image.Image, low_threshold: int = 100, high_threshold: int = 200) -> Image.Image:
    arr = np.array(image.convert("RGB"))
    edges = cv2.Canny(arr, low_threshold, high_threshold)
    edges_rgb = np.stack([edges] * 3, axis=-1)
    return Image.fromarray(edges_rgb)


def extract_pose(image: Image.Image) -> Image.Image:
    detector = _load_openpose()
    return detector(image.convert("RGB"))


# Checkpoints ControlNet SD1.5 correspondientes a cada tipo de control.
CONTROLNET_MODEL_IDS = {
    "edges": "lllyasviel/control_v11p_sd15_canny",
    "pose": "lllyasviel/control_v11p_sd15_openpose",
}


def build_control_image(reference_image: Image.Image, control_type: str) -> Image.Image:
    if control_type == "edges":
        return extract_edges(reference_image)
    if control_type == "pose":
        return extract_pose(reference_image)
    raise ValueError(f"control_type desconocido: {control_type}. Opciones: {list(CONTROLNET_MODEL_IDS)}")

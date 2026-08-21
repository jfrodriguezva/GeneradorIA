"""Face-swap: reemplaza el rostro de una persona en una foto por el de otra.

Usa InsightFace (detección/análisis de rostro) + inswapper (red de intercambio),
ambos corren sobre onnxruntime en CPU — es mucho más rápido que un pipeline de
difusión porque es una red pequeña y especializada, no un modelo generativo completo.
"""

import base64
import io
import os

import cv2
import numpy as np
from fastapi import HTTPException
from PIL import Image
from pydantic import BaseModel

FACESWAP_MODELS_ROOT = os.environ.get(
    "GENERATIVA_FACESWAP_MODELS_ROOT",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "faceswap-models"),
)
MODEL_PATH = os.path.join(FACESWAP_MODELS_ROOT, "inswapper_128.onnx")

_face_analyser = None
_face_swapper = None


class FaceSwapRequest(BaseModel):
    source_image_base64: str  # foto de la persona cuyo rostro se va a usar
    target_image_base64: str  # foto donde se va a colocar ese rostro


def _load_models():
    global _face_analyser, _face_swapper
    if _face_analyser is not None and _face_swapper is not None:
        return

    if not os.path.isfile(MODEL_PATH):
        raise HTTPException(
            status_code=503,
            detail=f"No se encontró el modelo de face-swap en {MODEL_PATH}. "
            "Descárgalo antes de usar esta función.",
        )

    from insightface.app import FaceAnalysis
    from insightface.model_zoo import get_model

    print(f"[faceswap] Cargando modelo de análisis de rostro (buffalo_l) desde {FACESWAP_MODELS_ROOT}...")
    analyser = FaceAnalysis(name="buffalo_l", root=FACESWAP_MODELS_ROOT, providers=["CPUExecutionProvider"])
    analyser.prepare(ctx_id=0, det_size=(640, 640))

    print(f"[faceswap] Cargando modelo de intercambio desde {MODEL_PATH}...")
    swapper = get_model(MODEL_PATH, providers=["CPUExecutionProvider"])

    _face_analyser = analyser
    _face_swapper = swapper
    print("[faceswap] Modelos listos")


def _decode_image(image_base64: str):
    try:
        raw = base64.b64decode(image_base64)
        pil_image = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer la imagen: {exc}")
    return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)


def swap_faces(req: FaceSwapRequest) -> dict:
    _load_models()

    source_bgr = _decode_image(req.source_image_base64)
    target_bgr = _decode_image(req.target_image_base64)

    source_faces = _face_analyser.get(source_bgr)
    if not source_faces:
        raise HTTPException(status_code=400, detail="No se detectó ningún rostro en la foto de origen.")

    target_faces = _face_analyser.get(target_bgr)
    if not target_faces:
        raise HTTPException(status_code=400, detail="No se detectó ningún rostro en la foto de destino.")

    source_face = max(source_faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

    result_bgr = target_bgr.copy()
    for target_face in target_faces:
        result_bgr = _face_swapper.get(result_bgr, target_face, source_face, paste_back=True)

    result_rgb = cv2.cvtColor(result_bgr, cv2.COLOR_BGR2RGB)
    result_image = Image.fromarray(result_rgb)

    buffer = io.BytesIO()
    result_image.save(buffer, format="PNG")
    image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return {"image_base64": image_base64, "format": "png", "faces_swapped": len(target_faces)}

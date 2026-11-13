"""Suite de pruebas End-to-End (E2E) para todos los endpoints de worker-python/image.

Prueba de punta a punta todo lo que estaba pendiente de validar en GPU:
1. GET  /health
2. POST /generate (txt2img + hires_fix + restore_faces GFPGAN + upscale Full HD)
3. POST /edit (img2img)
4. POST /inpaint (segmentación automática con SegFormer: mask_target="ropa" y "fondo" + hires_fix)
5. POST /generate-controlled (ControlNet: control_type="pose" OpenPose y "edges" Canny)
6. POST /generate-with-reference (IP-Adapter: mantener identidad facial en escena nueva)
7. POST /faceswap (InsightFace + inswapper_128 + restauración facial GFPGAN)
8. POST /upscale (OpenCV dnn_superres FSRCNN x4 a Full HD)

Uso:
    python worker-python/image/test_e2e_endpoints.py --url http://127.0.0.1:8002 --steps 25
"""

import argparse
import base64
import io
import json
import os
import time
import urllib.error
import urllib.request
from PIL import Image


def post_json(base_url: str, path: str, payload: dict, timeout: int = 1800) -> tuple[dict, float]:
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "ngrok-skip-browser-warning": "true",
        },
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} en {path}: {err_body}") from exc
    elapsed = time.perf_counter() - t0
    return body, elapsed


def get_json(base_url: str, path: str, timeout: int = 30) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    req = urllib.request.Request(url, headers={"ngrok-skip-browser-warning": "true"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def save_b64_image(b64_str: str, out_path: str) -> tuple[int, int]:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    raw = base64.b64decode(b64_str)
    img = Image.open(io.BytesIO(raw))
    img.save(out_path)
    return img.size


def run_suite(base_url: str, out_dir: str, steps: int = 25) -> list[dict]:
    os.makedirs(out_dir, exist_ok=True)
    results = []

    print(f"=== Verificando /health en {base_url} ===")
    health = get_json(base_url, "/health")
    print(f"[OK] /health -> {health}\n")

    # 1. /generate (Persona 1: base para edición, inpaint, controlnet, ip-adapter y destino de faceswap)
    print("1/8 Probando POST /generate (retrato base + hires_fix + restore_faces + upscale)...")
    gen1_resp, t_gen1 = post_json(
        base_url,
        "/generate",
        {
            "prompt": "portrait photo of a 30 year old woman wearing a blue denim jacket in a city park, natural pose",
            "steps": steps,
            "guidance_scale": 7.5,
            "width": 512,
            "height": 768,
            "seed": 42,
            "hires_fix": True,
            "restore_faces": True,
            "upscale": True,
        },
    )
    base_person_b64 = gen1_resp["image_base64"]
    w, h = save_b64_image(base_person_b64, os.path.join(out_dir, "01_generate_base.png"))
    print(f"    -> [OK] {w}x{h}px en {t_gen1:.2f}s")
    results.append({"test": "1. /generate (hires_fix + GFPGAN + upscale)", "status": "OK", "seconds": round(t_gen1, 2), "size": f"{w}x{h}"})

    # 2. /generate (Persona 2: rostro origen para /faceswap)
    print("2/8 Generando segundo rostro para prueba de /faceswap...")
    gen2_resp, t_gen2 = post_json(
        base_url,
        "/generate",
        {
            "prompt": "close-up portrait photo of a 28 year old woman with freckles and green eyes, studio lighting",
            "steps": steps,
            "guidance_scale": 7.5,
            "width": 512,
            "height": 768,
            "seed": 123,
            "hires_fix": False,
            "restore_faces": True,
            "upscale": False,
        },
    )
    source_face_b64 = gen2_resp["image_base64"]
    w, h = save_b64_image(source_face_b64, os.path.join(out_dir, "02_source_face.png"))
    print(f"    -> [OK] {w}x{h}px en {t_gen2:.2f}s")
    results.append({"test": "2. /generate (rostro origen)", "status": "OK", "seconds": round(t_gen2, 2), "size": f"{w}x{h}"})

    # 3. /edit (img2img)
    print("3/8 Probando POST /edit (img2img)...")
    edit_resp, t_edit = post_json(
        base_url,
        "/edit",
        {
            "image_base64": base_person_b64,
            "prompt": "portrait photo of a woman wearing a jacket in a snowy winter forest at sunset",
            "strength": 0.55,
            "steps": steps,
            "guidance_scale": 7.5,
            "seed": 42,
            "hires_fix": False,
            "restore_faces": True,
            "upscale": True,
        },
    )
    w, h = save_b64_image(edit_resp["image_base64"], os.path.join(out_dir, "03_edit_img2img.png"))
    print(f"    -> [OK] {w}x{h}px en {t_edit:.2f}s")
    results.append({"test": "3. /edit (img2img)", "status": "OK", "seconds": round(t_edit, 2), "size": f"{w}x{h}"})

    # 4. /inpaint (segmentación automática de ropa con SegFormer + recorte + hires_fix)
    print("4/8 Probando POST /inpaint (mask_target='ropa' con SegFormer + hires_fix)...")
    inpaint_resp, t_inpaint = post_json(
        base_url,
        "/inpaint",
        {
            "image_base64": base_person_b64,
            "prompt": "elegant red satin evening blazer, luxury fabric texture",
            "mask_target": "ropa",
            "strength": 0.95,
            "steps": steps,
            "guidance_scale": 7.5,
            "seed": 42,
            "hires_fix": True,
            "restore_faces": True,
            "upscale": True,
        },
    )
    w, h = save_b64_image(inpaint_resp["image_base64"], os.path.join(out_dir, "04_inpaint_ropa.png"))
    print(f"    -> [OK] {w}x{h}px en {t_inpaint:.2f}s")
    results.append({"test": "4. /inpaint (mask_target=ropa + hires_fix)", "status": "OK", "seconds": round(t_inpaint, 2), "size": f"{w}x{h}"})

    # 5. /generate-controlled (ControlNet OpenPose)
    print("5/8 Probando POST /generate-controlled (ControlNet control_type='pose')...")
    ctrl_pose_resp, t_pose = post_json(
        base_url,
        "/generate-controlled",
        {
            "reference_image_base64": base_person_b64,
            "control_type": "pose",
            "prompt": "woman wearing a white linen dress on a tropical beach at golden hour",
            "controlnet_conditioning_scale": 1.0,
            "steps": steps,
            "guidance_scale": 7.5,
            "seed": 42,
            "restore_faces": True,
            "upscale": True,
        },
    )
    w, h = save_b64_image(ctrl_pose_resp["image_base64"], os.path.join(out_dir, "05_controlnet_pose.png"))
    print(f"    -> [OK] {w}x{h}px en {t_pose:.2f}s")
    results.append({"test": "5. /generate-controlled (OpenPose)", "status": "OK", "seconds": round(t_pose, 2), "size": f"{w}x{h}"})

    # 6. /generate-controlled (ControlNet Canny Edges)
    print("6/8 Probando POST /generate-controlled (ControlNet control_type='edges')...")
    ctrl_edges_resp, t_edges = post_json(
        base_url,
        "/generate-controlled",
        {
            "reference_image_base64": base_person_b64,
            "control_type": "edges",
            "prompt": "cyberpunk portrait with neon lights and leather jacket, rainy night",
            "controlnet_conditioning_scale": 0.85,
            "steps": steps,
            "guidance_scale": 7.5,
            "seed": 42,
            "restore_faces": True,
            "upscale": True,
        },
    )
    w, h = save_b64_image(ctrl_edges_resp["image_base64"], os.path.join(out_dir, "06_controlnet_edges.png"))
    print(f"    -> [OK] {w}x{h}px en {t_edges:.2f}s")
    results.append({"test": "6. /generate-controlled (Canny edges)", "status": "OK", "seconds": round(t_edges, 2), "size": f"{w}x{h}"})

    # 7. /generate-with-reference (IP-Adapter Full Face)
    print("7/8 Probando POST /generate-with-reference (IP-Adapter identidad en nueva escena)...")
    ipa_resp, t_ipa = post_json(
        base_url,
        "/generate-with-reference",
        {
            "reference_image_base64": base_person_b64,
            "prompt": "woman sitting at a parisian cafe drinking coffee,wearing a black turtleneck",
            "ip_adapter_scale": 0.65,
            "steps": steps,
            "guidance_scale": 7.5,
            "width": 512,
            "height": 768,
            "seed": 42,
            "restore_faces": True,
            "upscale": True,
        },
    )
    w, h = save_b64_image(ipa_resp["image_base64"], os.path.join(out_dir, "07_ipadapter_reference.png"))
    print(f"    -> [OK] {w}x{h}px en {t_ipa:.2f}s")
    results.append({"test": "7. /generate-with-reference (IP-Adapter)", "status": "OK", "seconds": round(t_ipa, 2), "size": f"{w}x{h}"})

    # 8. /faceswap + /upscale
    print("8/8 Probando POST /faceswap (InsightFace + inswapper + GFPGAN) y POST /upscale...")
    swap_resp, t_swap = post_json(
        base_url,
        "/faceswap",
        {
            "source_image_base64": source_face_b64,
            "target_image_base64": base_person_b64,
            "restore_face": True,
        },
    )
    w, h = save_b64_image(swap_resp["image_base64"], os.path.join(out_dir, "08_faceswap_gfpgan.png"))
    print(f"    -> [OK] /faceswap: faces_swapped={swap_resp.get('faces_swapped')}, restored={swap_resp.get('restored')} ({w}x{h}px) en {t_swap:.2f}s")
    results.append({
        "test": f"8a. /faceswap (restored={swap_resp.get('restored')})",
        "status": "OK",
        "seconds": round(t_swap, 2),
        "size": f"{w}x{h}",
    })

    up_resp, t_up = post_json(
        base_url,
        "/upscale",
        {"image_base64": source_face_b64},
    )
    w_u, h_u = save_b64_image(up_resp["image_base64"], os.path.join(out_dir, "09_upscale_fullhd.png"))
    print(f"    -> [OK] /upscale: {w_u}x{h_u}px en {t_up:.2f}s")
    results.append({"test": "8b. /upscale (FSRCNN Full HD)", "status": "OK", "seconds": round(t_up, 2), "size": f"{w_u}x{h_u}"})

    report_path = os.path.join(out_dir, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"status": "completed", "results": results}, f, indent=2, ensure_ascii=False)

    print("\n=== RESUMEN DE PRUEBAS E2E ===")
    for r in results:
        print(f"  [{r['status']}] {r['test']:<45} | {r['seconds']:>6.2f}s | {r['size']}")
    print(f"\nImágenes guardadas en: {os.path.abspath(out_dir)}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pruebas E2E del Worker de Imágenes de Generativa")
    parser.add_argument("--url", default="http://127.0.0.1:8002", help="URL base del worker (default: http://127.0.0.1:8002)")
    parser.add_argument("--out-dir", default="test_outputs", help="Carpeta donde guardar las imágenes generadas")
    parser.add_argument("--steps", type=int, default=25, help="Pasos de inferencia por prueba (default: 25)")
    args = parser.parse_args()

    run_suite(args.url, args.out_dir, args.steps)

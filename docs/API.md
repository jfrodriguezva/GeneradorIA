# Referencia de API

Todo lo que el frontend puede pedir. Tres capas: frontend → API C# (proxy puro) → workers
Python (la IA real). Los tipos de request/response son los definidos en el código — no
inventados.

## API C# (puerto 20000) — capa de proxy

CORS restringido a `localhost:20001`/`127.0.0.1:20001`. Timeouts del cliente HTTP hacia los
workers: 5 min para chat, 45 min para imágenes (subido de 20 min tras un timeout real en uso
normal con hires_fix+restore_faces+strength alto combinados). `GET /health` a nivel de app
(no de controller).

| Método | Ruta | Body (`Models/*.cs`) | Reenvía a | Notas |
|---|---|---|---|---|
| GET | `/api/chat/health` | — | `GET {chat}/health` | passthrough |
| POST | `/api/chat` | `ChatRequest{messages:[{role,content}], stream=true, temperature=0.7, maxTokens=1024}` | `POST {chat}/chat` | si `stream`, reenvía SSE byte a byte; si no, JSON |
| GET | `/api/image/health` | — | `GET {image}/health` | passthrough |
| POST | `/api/image/generate` | `GenerateImageRequest{prompt, negativePrompt?, steps=50, guidanceScale=7.5, width=512, height=768, seed?, upscale=true, hiresFix=false, restoreFaces=false}` | `POST {image}/generate` | |
| POST | `/api/image/edit` | `EditImageRequest{imageBase64, prompt, negativePrompt?, strength=0.6, steps=50, guidanceScale=7.5, seed?, upscale=true, hiresFix=false, restoreFaces=false}` | `POST {image}/edit` | |
| POST | `/api/image/inpaint` | `InpaintRequest{imageBase64, prompt, negativePrompt?, maskBase64?, maskTarget?, strength=0.9, steps=50, guidanceScale=7.5, seed?, upscale=true}` | `POST {image}/inpaint` | requiere `maskBase64` o `maskTarget` |
| POST | `/api/image/generate-controlled` | `ControlledGenerateRequest{referenceImageBase64, controlType="pose", prompt, negativePrompt?, controlnetConditioningScale=1.0, steps=50, guidanceScale=7.5, seed?, upscale=true}` | `POST {image}/generate-controlled` | |
| POST | `/api/image/generate-with-reference` | `ReferenceGenerateRequest{referenceImageBase64, prompt, negativePrompt?, ipAdapterScale=0.6, steps=30, guidanceScale=7.5, width=512, height=768, seed?, upscale=true}` | `POST {image}/generate-with-reference` | |
| POST | `/api/image/faceswap` | `FaceSwapRequest{sourceImageBase64, targetImageBase64, restoreFace=true}` | `POST {image}/faceswap` | |
| POST | `/api/image/upscale` | `UpscaleRequest{imageBase64}` | `POST {image}/upscale` | |

Todos los endpoints de imagen deserializan la respuesta del worker y la devuelven con el mismo
status code (503 si el worker no responde).

## Worker de chat (FastAPI, puerto 8011)

- `GET /health` → `{status, model_loaded}`
- `POST /load` — `LoadRequest{model_path, n_ctx=4096, n_threads=null}`. Carga otro GGUF en
  caliente. 400 si el archivo no existe.
- `POST /chat` — `ChatRequest{messages:[{role: system|user|assistant, content}], stream=true,
  temperature=0.7, max_tokens=1024}`. Sin streaming devuelve el dict crudo de `llama_cpp`; con
  streaming devuelve SSE (`data: {"content": "..."}\n\n`, termina en `data: [DONE]`). 503 si no
  hay modelo cargado.

Config vía variables de entorno: `GENERATIVA_MODEL_PATH` (vacío = carga perezosa vía `/load`),
`GENERATIVA_N_CTX=4096`, `GENERATIVA_N_THREADS=os.cpu_count()`.

## Worker de imágenes (FastAPI, puerto 8002)

- `GET /health` → `{status, model_loaded, device}`
- `POST /generate` — `GenerateRequest{prompt, negative_prompt?, steps=50, guidance_scale=7.5,
  width=512, height=768, seed?, upscale=true, hires_fix=false, restore_faces=false}` →
  `{image_base64, format:"png", width, height}`. `hires_fix` corre una segunda pasada de
  refinamiento (`_apply_hires_fix`: reescala 1.5x y reinyecta vía img2img con strength=0.4,
  ~30-40% más lento). `restore_faces` pasa GFPGAN sobre el resultado (no solo en /faceswap);
  requiere `GFPGANv1.4.pth`, si falta se ignora sin error.
- `POST /edit` — `EditRequest{image_base64, prompt, negative_prompt?, strength=0.6, steps=50,
  guidance_scale=7.5, seed?, upscale=true, hires_fix=false, restore_faces=false}` → misma forma
  de respuesta; la imagen de entrada se redimensiona al lado mayor 768px (redondeado a múltiplo
  de 8); `hires_fix`/`restore_faces` igual que en `/generate`
- `POST /inpaint` — `InpaintRequest{image_base64, prompt, negative_prompt?, mask_base64?,
  mask_target?, strength=0.97, steps=50, guidance_scale=7.5, seed?, upscale=true}` → edita solo
  la zona indicada dejando el resto de la imagen intacto (recorta la zona de la máscara con
  margen, genera solo ahí a resolución completa del modelo y la pega de vuelta con blending —
  `_run_inpaint_cropped` — para evitar el artefacto de "doble exposición" que daba correr el
  inpainting sobre la imagen completa). `mask_target` genera la máscara solo
  (segmentación con SegFormer, `worker-python/image/segmentation.py`): `"ropa"`, `"fondo"`,
  `"persona"` o `"rostro"`; alternativamente se puede pasar `mask_base64` ya dibujada a mano
  (blanco = zona a editar). 400 si no se manda ninguna de las dos.
- `POST /generate-controlled` — `ControlledGenerateRequest{reference_image_base64,
  control_type="pose", prompt, negative_prompt?, controlnet_conditioning_scale=1.0, steps=50,
  guidance_scale=7.5, seed?, upscale=true}` → genera una escena nueva conservando la pose
  (`control_type="pose"`, vía OpenPose de `controlnet_aux`) o los contornos (`"edges"`, Canny)
  de `reference_image_base64`. No conserva el rostro/identidad — para eso combinar con
  `/faceswap` después. **Corre en torch CPU puro, no OpenVINO** (ver nota de internals).
- `POST /generate-with-reference` — `ReferenceGenerateRequest{reference_image_base64, prompt,
  negative_prompt?, ip_adapter_scale=0.6, steps=30, guidance_scale=7.5, width=512, height=768,
  seed?, upscale=true}` → genera una escena nueva a partir del prompt manteniendo la identidad
  de la persona en `reference_image_base64` (IP-Adapter, `h94/IP-Adapter`
  `ip-adapter-full-face_sd15.bin`). Distinto de face-swap: aquí la escena se genera desde cero,
  no se pega un rostro sobre una foto existente. **Corre en torch CPU puro, no OpenVINO.**
- `POST /faceswap` — `FaceSwapRequest{source_image_base64, target_image_base64,
  restore_face=true}` → resultado del swap; 503 si falta `inswapper_128.onnx` en
  `faceswap-models/`. Con `restore_face=true` (default), re-renderiza el rostro con GFPGAN para
  que se mezcle con la iluminación/textura de la foto; si falta `GFPGANv1.4.pth` en
  `faceswap-models/`, se omite este paso sin dar error (`restored: false` en la respuesta).
- `POST /upscale` — `{image_base64}` → FSRCNN x4 y luego recorte a lado mayor 1920px (el
  parámetro `target_long_side` no está expuesto vía API)

**Internals que afectan la calidad**: scheduler forzado `DPMSolverMultistepScheduler`
(`algorithm_type="dpmsolver++"`, `final_sigmas_type="sigma_min"`). Se le agrega automáticamente
un sufijo de calidad a todo prompt (`", professional photography, ultra detailed, sharp focus,
high quality, 8k uhd, natural lighting"`). Si no mandas `negative_prompt`, usa uno por defecto
orientado a evitar artefactos de anatomía típicos de SD1.5. Ver [`CAPACIDADES.md`](./CAPACIDADES.md)
para el análisis completo de calidad.

Config vía variables de entorno: `GENERATIVA_IMAGE_MODEL_ID` (default
`emilianJR/epiCRealism`), `GENERATIVA_IMAGE_OV_DIR`,
`GENERATIVA_IMAGE_DEVICE=CPU` (también acepta `GPU`/`AUTO` si hay iGPU Intel),
`GENERATIVA_UPSCALE_MODEL_PATH`, `GENERATIVA_GFPGAN_MODEL_PATH`.

**`/generate`, `/edit`, `/inpaint` van por OpenVINO (acelerados); `/generate-controlled` y
`/generate-with-reference` van por torch CPU puro** — optimum-intel 1.22.0 no tiene soporte
estable de ControlNet ni IP-Adapter para SD1.5, solo para SD3/SDXL. Son notablemente más lentos
que los otros tres endpoints en el mismo hardware. Si optimum-intel agrega ese soporte en el
futuro, `_load_controlnet_pipeline`/`_load_ipadapter_pipeline` en `main.py` son el punto a
migrar para recuperar la aceleración.

## Qué expone realmente el frontend

Importante: la API acepta más de lo que la UI deja tocar.

- **`steps` y `guidance_scale` están hardcodeados en el frontend** (`steps: 50, guidanceScale:
  7.5` en `frontend-nextjs/src/app/imagenes/page.tsx`) — no son ajustables desde la UI, aunque
  la API sí los soporta.
- Controles que sí expone la UI: prompt, negative prompt opcional, un dropdown de encuadre
  (`retrato` 512×768, `cuerpoCompleto` 512×896, `cuadrado` 768×768, `horizontal` 896×512 — fija
  width/height), checkbox "Escalar a Full HD" (`upscale`, default `true`), y en modo edición un
  slider de `strength` (0.2–0.9, paso 0.05, default 0.6).
- Face-swap solo expone los dos inputs de archivo, sin parámetros.
- `seed` nunca se envía desde el frontend (siempre aleatorio) — hay que llamar la API
  directamente para fijar una semilla reproducible.

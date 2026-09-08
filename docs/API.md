# Referencia de API

Todo lo que el frontend puede pedir. Tres capas: frontend → API C# (proxy puro) → workers
Python (la IA real). Los tipos de request/response son los definidos en el código — no
inventados.

## API C# (puerto 20000) — capa de proxy

CORS restringido a `localhost:20001`/`127.0.0.1:20001`. Timeouts del cliente HTTP hacia los
workers: 5 min para chat, 20 min para imágenes. `GET /health` a nivel de app (no de controller).

| Método | Ruta | Body (`Models/*.cs`) | Reenvía a | Notas |
|---|---|---|---|---|
| GET | `/api/chat/health` | — | `GET {chat}/health` | passthrough |
| POST | `/api/chat` | `ChatRequest{messages:[{role,content}], stream=true, temperature=0.7, maxTokens=1024}` | `POST {chat}/chat` | si `stream`, reenvía SSE byte a byte; si no, JSON |
| GET | `/api/image/health` | — | `GET {image}/health` | passthrough |
| POST | `/api/image/generate` | `GenerateImageRequest{prompt, negativePrompt?, steps=50, guidanceScale=7.5, width=512, height=768, seed?, upscale=true}` | `POST {image}/generate` | |
| POST | `/api/image/edit` | `EditImageRequest{imageBase64, prompt, negativePrompt?, strength=0.6, steps=50, guidanceScale=7.5, seed?, upscale=true}` | `POST {image}/edit` | |
| POST | `/api/image/faceswap` | `FaceSwapRequest{sourceImageBase64, targetImageBase64}` | `POST {image}/faceswap` | |
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
  width=512, height=768, seed?, upscale=true}` → `{image_base64, format:"png", width, height}`
- `POST /edit` — `EditRequest{image_base64, prompt, negative_prompt?, strength=0.6, steps=50,
  guidance_scale=7.5, seed?, upscale=true}` → misma forma de respuesta; la imagen de entrada se
  redimensiona al lado mayor 768px (redondeado a múltiplo de 8)
- `POST /faceswap` — `{source_image_base64, target_image_base64}` → resultado del swap; 503 si
  falta `inswapper_128.onnx` en `faceswap-models/`
- `POST /upscale` — `{image_base64}` → FSRCNN x4 y luego recorte a lado mayor 1920px (el
  parámetro `target_long_side` no está expuesto vía API)

**Internals que afectan la calidad**: scheduler forzado `DPMSolverMultistepScheduler`
(`algorithm_type="dpmsolver++"`, `final_sigmas_type="sigma_min"`). Se le agrega automáticamente
un sufijo de calidad a todo prompt (`", professional photography, ultra detailed, sharp focus,
high quality, 8k uhd, natural lighting"`). Si no mandas `negative_prompt`, usa uno por defecto
orientado a evitar artefactos de anatomía típicos de SD1.5. Ver [`CAPACIDADES.md`](./CAPACIDADES.md)
para el análisis completo de calidad.

Config vía variables de entorno: `GENERATIVA_IMAGE_MODEL_ID` (default
`SG161222/Realistic_Vision_V5.1_noVAE`), `GENERATIVA_IMAGE_OV_DIR`,
`GENERATIVA_IMAGE_DEVICE=CPU` (también acepta `GPU`/`AUTO` si hay iGPU Intel),
`GENERATIVA_UPSCALE_MODEL_PATH`.

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

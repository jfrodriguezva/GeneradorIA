# Generativa

Suite de IA generativa 100% local (sin servicios externos, sin API keys): chat, generación de
imágenes, edición de imágenes, face-swap. Todo corre en la máquina del usuario, pensado para
hardware **sin GPU dedicada** (CPU-only vía OpenVINO). Uso personal, consentido — ver sección
"Filtros de contenido" antes de asumir restricciones que no existen.

## Arquitectura

```
WPF Host (Generativa.Host.exe)
  └─ WebView2 → apunta a http://127.0.0.1:20001 (frontend)
  └─ Lanza y vigila los 4 procesos de abajo (ver ServiceOrchestrator.cs)

Next.js frontend (puerto 20001)
  └─ fetch() → API C#

API C# / ASP.NET Core (puerto 20000)
  └─ proxy HTTP → workers Python (no tiene lógica de IA propia)

Worker chat Python (puerto 8011) — worker-python/chat/main.py
  └─ llama-cpp-python + Qwen2.5-3B-Instruct GGUF (CPU)

Worker imágenes Python (puerto 8002) — worker-python/image/main.py
  └─ optimum-intel (OpenVINO) + Realistic_Vision_V5.1_noVAE (SD1.5)
  └─ txt2img, img2img (edición), face-swap (InsightFace+inswapper), upscale (OpenCV FSRCNN)
```

**Por qué está separado así**: la API en C# es un simple router/proxy sin IA — así el frontend
nunca habla directo con Python. Cada worker Python es un proceso independiente para poder
reiniciarlos sin tumbar todo, y porque cada uno tiene su propio venv con dependencias pesadas
distintas (`.venv` para chat, `.venv-image` para imágenes — no se comparten).

## Cómo correr en desarrollo

```powershell
powershell -File start-dev.ps1
```

Levanta los 4 servicios en ventanas separadas. Luego, aparte: `cd host-wpf/Generativa.Host && dotnet run`
(o simplemente confía en que el propio WPF los levanta solo si no están corriendo — ver
`ServiceOrchestrator.cs`, hace health-check antes de lanzar cada uno).

## Puertos

| Servicio | Puerto | Nota |
|---|---|---|
| API C# | 20000 | |
| Frontend Next.js | 20001 | |
| Worker chat | 8011 | **No usar 8001** — choca con otro proyecto del usuario (`SportsPredictor ML Service`) que corre en esta máquina de desarrollo. Si migras a otra máquina sin ese conflicto, puedes usar el puerto que quieras, pero mantén consistencia en todos los archivos. |
| Worker imágenes | 8002 | |

## Modelos usados y por qué

- **Chat**: `Qwen2.5-3B-Instruct` GGUF Q4_K_M (~2GB) vía `llama-cpp-python`. Elegido por ser
  pequeño/rápido para validar la plomería; se puede subir a un modelo más grande si el hardware
  lo permite (más RAM/CPU o GPU).
- **Imágenes**: `SG161222/Realistic_Vision_V5.1_noVAE` (arquitectura SD1.5) en vez de SD-Turbo
  (que se probó primero pero da calidad muy inferior, solo 1 paso). Este modelo da mucho mejor
  fotorrealismo/anatomía a costa de velocidad: **8-14 min por imagen a 20-30 pasos, 512x768,
  en CPU sin GPU dedicada**. A 60 pasos (más calidad para escenas complejas) puede tardar 15-20 min.
- **Face-swap**: InsightFace `buffalo_l` (análisis de rostro) + `inswapper_128.onnx`
  (intercambio). Corre en CPU vía onnxruntime, **segundos** por swap — mucho más rápido que
  difusión porque es una red pequeña especializada, no un modelo generativo completo.
- **Escalado a Full HD**: OpenCV `dnn_superres` con FSRCNN x4 (no Real-ESRGAN — ese paquete
  tiene conflictos conocidos de `basicsr`/`torchvision` con versiones nuevas de PyTorch).
  ~1-2 segundos por imagen, escala y luego recorta al lado largo en 1920px preservando aspecto.
- **Segmentación (para inpainting dirigido)**: `mattmdjaga/segformer_b2_clothes` vía
  `transformers` — separa ropa/persona/fondo/rostro para generar la máscara sola sin que el
  usuario tenga que dibujarla. Ver `worker-python/image/segmentation.py`.
- **Inpainting**: mismo checkpoint que `/generate`/`/edit` (Realistic Vision), vía
  `OVStableDiffusionInpaintPipeline` (sí soportado en OpenVINO/optimum-intel para SD1.5, a
  diferencia de ControlNet e IP-Adapter — ver más abajo). Al no ser un checkpoint
  "inpainting-specific" corre en modo "legacy" (mezcla de latentes según la máscara).
- **ControlNet** (conservar pose/bordes al cambiar ropa o escenario): `lllyasviel/control_v11p_sd15_openpose`
  (pose, vía `controlnet_aux`) y `lllyasviel/control_v11p_sd15_canny` (bordes, solo OpenCV).
  **No corre en OpenVINO**: `optimum-intel==1.22.0` no expone `OVStableDiffusionControlNetPipeline`
  para SD1.5 (verificado en este entorno — solo existe para SD3/SDXL), así que
  `_load_controlnet_pipeline` en `main.py` usa `diffusers` puro en torch CPU. Más lento que el
  resto de endpoints; si optimum-intel agrega ese soporte, migrar para recuperar velocidad.
- **IP-Adapter** (mantener la identidad de una persona en escenas nuevas): `h94/IP-Adapter`
  (`ip-adapter-full-face_sd15.bin`). Mismo problema que ControlNet — sin soporte estable en
  optimum-intel para SD1.5 — así que `_load_ipadapter_pipeline` también va por torch CPU puro.
- **Restauración facial post face-swap**: GFPGAN (`GFPGANv1.4.pth`, descarga manual opcional en
  `faceswap-models/`) para que el rostro intercambiado se mezcle con luz/textura en vez de
  notarse "pegado". Corre en segundos vía onnxruntime/torch CPU, igual de rápido que el swap.

## Filtros de contenido

El `safety_checker` de Stable Diffusion está **desactivado a propósito** (decisión explícita del
usuario desde el inicio del proyecto: uso personal, contenido consentido). El software, tal
como está, no tiene ningún filtro de contenido — generará/editará lo que se le pida dentro de
su capacidad técnica. Eso no cambia lo que es legal usar (contenido de menores, imágenes íntimas
no consentidas de personas reales identificables, etc. siguen siendo ilegales sin importar que
no haya filtro técnico). Si retomas este proyecto: esto sigue siendo así a propósito, no es un
bug ni algo que "arreglar".

## Video — explícitamente NO implementado (pendiente, hardware-dependiente)

El usuario pidió generación de video (ej. animar una foto, clips cortos) pero se descartó por
ahora: **no es viable en CPU sin GPU dedicada** — un solo frame ya tarda minutos, un clip de
30s tardaría horas/días. Queda pendiente para cuando el usuario tenga una máquina con GPU NVIDIA
(mínimo 8GB VRAM, idealmente 12GB+). No empezar esto sin confirmar que el hardware disponible
tiene GPU dedicada real.

## Lecciones aprendidas (para no repetir el mismo debugging)

1. **`llama-cpp-python` no compila con MSVC** (error de `<chrono>` en llama.cpp vendored). Usar
   el índice de wheels precompiladas: `pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu`
2. **Conflicto `openvino`/`nncf`/`optimum-intel`**: `openvino>=2026.0` eliminó `openvino.runtime`
   que `optimum-intel` 1.22.0 todavía usa → pin `openvino<2026`. Eso rompe `nncf>=3.x` (usa
   `Type.u2`, no existe antes de 2026) → pin `nncf==2.14.1`. Ver `worker-python/image/requirements.txt`.
3. **Red corporativa con inspección TLS (MITM)**: `requests`/`urllib3` (usan `certifi`) no
   confían en el certificado raíz corporativo aunque Windows sí. Arreglado con `pip-system-certs`
   (parcha `ssl` para usar el almacén de certificados de Windows). Sin esto, las descargas de
   HuggingFace vía `huggingface_hub` fallan con `SSLCertVerificationError`.
4. **`torch` por defecto en pip es enorme** (build con CUDA aunque no se use) → instalar con
   `pip install torch --index-url https://download.pytorch.org/whl/cpu`.
5. **MAX_PATH de Windows**: la carpeta de licencias de terceros de `torch`
   (`*.dist-info\licenses\third_party\...`) tiene rutas muy anidadas que, combinadas con una
   ruta de proyecto larga, superan 260 caracteres → excluir `*.dist-info\licenses\*` al empaquetar.
6. **Inno Setup**: un solo `.exe` no puede pasar de ~4.2GB → `DiskSpanning=yes` +
   `DiskSliceSize=max` (genera un `.exe` + un `.bin`, deben copiarse juntos).
7. **`.next/cache` y `.next/dev`** son artefactos de `npm run dev`, no de producción — si el
   dev server sigue corriendo cuando compilas el instalador, Inno Setup puede toparse con un
   archivo bloqueado (`lock`). Excluidos del instalador.
8. **Next.js 15+ bloquea peticiones cross-origin en dev** si accedes por `127.0.0.1` en vez de
   `localhost` → `allowedDevOrigins: ["127.0.0.1", "localhost"]` en `next.config.ts`.
9. **Procesos en segundo plano mueren solos entre turnos de Claude Code** en este entorno
   (aparente límite de sesión). No es un bug del código — si un servicio no responde, simplemente
   reinícialo. `opencv-python` y `opencv-contrib-python-headless` (o su variante headless) **no
   deben coexistir** — `dnn_superres` solo viene en el paquete "contrib".
10. **Git Bash en Windows convierte flags que empiezan con `/`** (ej. `/VERYSILENT`) en rutas de
    archivo. Usar `MSYS_NO_PATHCONV=1` antes del comando, o doble slash (`//VERYSILENT`).
11. **`basicsr` (dependencia de `gfpgan`) importa `torchvision.transforms.functional_tensor`**,
    un módulo interno que torchvision quitó en 0.17+ (movido a `torchvision.transforms.functional`).
    Es el mismo conflicto de la lección de Real-ESRGAN de arriba, pero esta vez GFPGAN sí hacía
    falta (no hay alternativa igual de buena solo con OpenCV para restauración facial) — en vez
    de fijar una versión vieja de torchvision, se parchea el módulo faltante en tiempo de
    ejecución antes del import (`_patch_basicsr_torchvision_compat` en
    `worker-python/image/faceswap.py`).
12. **`controlnet_aux` (para ControlNet) declara `opencv-python-headless` como dependencia**,
    que no debe coexistir con `opencv-contrib-python-headless` (misma lección #9). El orden de
    resolución de `pip install -r requirements.txt` no garantiza cuál "gana" en disco — hay que
    reinstalar el paquete correcto al final: `pip install --force-reinstall --no-deps
    opencv-contrib-python-headless` (ya automatizado en `installer/setup-environment.ps1`).
13. **`optimum-intel==1.22.0` no tiene soporte de ControlNet ni IP-Adapter para SD1.5 vía
    OpenVINO** (`OVStableDiffusionControlNetPipeline`/`OVControlNetModel` no existen en esa
    versión — verificado en este entorno; ese soporte solo está para SD3/SDXL). `/generate-controlled`
    y `/generate-with-reference` corren en `diffusers` puro sobre torch CPU en vez de OpenVINO
    por esto — son notablemente más lentos que `/generate`, `/edit` e `/inpaint`. Si una versión
    futura de optimum-intel agrega ese soporte, migrar `_load_controlnet_pipeline`/
    `_load_ipadapter_pipeline` en `main.py`.

## Instalador (`installer/`)

`installer/generativa.iss` (Inno Setup 6) empaqueta:
- WPF host + API publicados como `.exe` self-contained (no necesitan .NET preinstalado)
- Código de los workers Python (no los venvs — se recrean en el equipo destino)
- Modelos ya descargados/convertidos (GGUF, OpenVINO IR, face-swap, upscale)
- Frontend Next.js compilado (`.next` + `node_modules` + `public`)
- `installer/setup-environment.ps1`: se ejecuta post-instalación, instala Python/Node.js vía
  `winget` si faltan (siempre la última versión estable), crea los venvs, instala dependencias.

Compilar: `"C:\Users\<usuario>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer\generativa.iss`
(usar **ruta absoluta** al script, la relativa falla de forma inconsistente en este entorno).
Tarda 20-50 min por el tamaño (~5-7GB, dominado por los modelos). **No correr generación de
imágenes al mismo tiempo que compilas el instalador** — la contención de CPU/RAM hace que el
worker de imágenes muera a medio proceso.

**Limitación real**: no es un instalador 100% portable a cualquier PC — necesita que el equipo
destino tenga `winget` (viene preinstalado en Windows 10/11 actualizados) para la instalación
automática de Python/Node.js. Pide privilegios de administrador (UAC).

## Estado del proyecto (última actualización de esta nota)

- ✅ Chat, generación de imágenes, edición (img2img), face-swap, escalado a Full HD — todo
  funcionando y probado de punta a punta.
- ✅ Instalador compilando con todos los modelos incluidos.
- ✅ Inpainting dirigido (`/inpaint`, cambiar solo ropa/fondo/persona/rostro con máscara
  automática por segmentación), ControlNet (`/generate-controlled`, conservar pose/bordes al
  cambiar escena), IP-Adapter (`/generate-with-reference`, mantener identidad en escena nueva) y
  restauración facial post face-swap (GFPGAN) — código escrito, sintaxis/imports verificados y
  dependencias instaladas y probadas en el venv de desarrollo (incluye el parche
  basicsr/torchvision y la reinstalación forzada de opencv-contrib, ver lecciones #11/#12).
  **Pendiente de correr una generación real de punta a punta de cada endpoint nuevo** (cada
  corrida en CPU tarda varios minutos, no se ejecutaron en esta sesión) y de descargar
  `GFPGANv1.4.pth` para probar la restauración facial.
- ⏳ Pendiente: validar el instalador en una máquina limpia distinta (el usuario lo va a probar
  en una ThinkPad sin GPU dedicada). Ahora también necesita validar que
  `setup-environment.ps1` instale bien las dependencias nuevas (torchvision, gfpgan/basicsr,
  controlnet_aux) en una máquina limpia.
- ⬜ Video: descartado por hardware, pendiente para cuando haya una GPU NVIDIA disponible.

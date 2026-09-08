# Recovery: contexto para retomar este proyecto en otro chat

Si estás leyendo esto en una sesión nueva de Claude Code sin memoria de las conversaciones
anteriores: este documento te pone al día rápido. El código ya vive en git (no hay que
reconstruir nada desde cero, a diferencia de `RECUPERACION-ia-imagenes.md`, que sí es un
proyecto hermano que se borró por completo). Esto es más bien un resumen de "quién es quién y
por qué está así".

## Origen

- Repo: `https://github.com/jfrodriguezva/GeneradorIA.git`
- Clonado en: `C:\jfrodriguezv\SourceCodeAnthropic\Personal\Generator`
- Owner del repo en GitHub: `jfrodriguezva`

## Qué es esto en una frase

Suite de IA generativa **100% local, sin API keys, sin GPU dedicada** (chat + generación/edición
de imágenes + face-swap + upscale), empaquetada como app de escritorio Windows (WPF + WebView2
sobre un frontend Next.js).

## Documentos de este repo y para qué sirve cada uno

| Archivo | Para qué |
|---|---|
| [`README.md`](./README.md) | Cómo levantar el proyecto en desarrollo, requisitos, primer setup |
| [`CLAUDE.md`](./CLAUDE.md) | Arquitectura técnica completa, decisiones de diseño, lecciones de debugging ya resueltas, notas del instalador |
| [`docs/API.md`](./docs/API.md) | Referencia completa de endpoints (API C# + los 2 workers Python), qué expone realmente el frontend vs. qué acepta la API |
| [`docs/CAPACIDADES.md`](./docs/CAPACIDADES.md) | Qué tan buena es la calidad de imagen/video hoy, por qué, y qué haría falta para subirla |
| [`docs/EVALUACION-PRODUCTO.md`](./docs/EVALUACION-PRODUCTO.md) | Qué tan funcional/vendible es esto hoy: análisis desde fotografía, ingeniería, UX y listo-para-equipo, con roadmap si se quisiera llevar a producto |
| `RECUPERACION-ia-imagenes.md` | **No es de este proyecto** — notas de recuperación de un proyecto hermano distinto (portal ComfyUI, SDXL/Qwen-Image-Edit/LTX-Video) que se borró. Útil como referencia de qué se probó ya en hardware similar. |
| Este archivo (`RECOVERY.md`) | Punto de entrada rápido para una sesión nueva |

**Orden de lectura recomendado si vuelves en frío**: este archivo → `README.md` (para poder
correrlo) → `CLAUDE.md` (para entender el porqué de las decisiones) → `docs/API.md` /
`docs/CAPACIDADES.md` según lo que necesites tocar.

## Arquitectura en una imagen mental

```
WPF Host (Windows, WebView2)
  └─ vigila y lanza 4 procesos (ServiceOrchestrator.cs)

Next.js (20001) → API C# (20000, solo proxy) → Worker chat Python (8011, llama-cpp-python + Qwen2.5-3B)
                                              → Worker imagen Python (8002, OpenVINO + SD1.5 + InsightFace + OpenCV)
```

Cada worker Python tiene su propio venv (`.venv` chat, `.venv-image` imagen) — no se comparten
dependencias.

## Decisiones deliberadas — no proponerlas como "bugs a arreglar"

1. **`safety_checker` desactivado.** Uso personal, contenido consentido, decisión explícita del
   usuario desde el inicio. Sigue siendo ilegal generar contenido ilegal (menores, imágenes
   íntimas no consentidas de personas reales), el filtro técnico o su ausencia no cambia eso.
2. **Video no implementado.** Se pidió, se evaluó, se descartó: en CPU sin GPU dedicada un solo
   frame ya tarda minutos, un clip de 30s tardaría horas/días. Pendiente hasta tener GPU NVIDIA
   (8GB+ VRAM). No arrancar esto sin confirmar hardware.
3. **Stable Diffusion 1.5 en vez de SDXL/FLUX/Qwen-Image.** Compromiso deliberado
   velocidad/calidad para CPU-only — ver `docs/CAPACIDADES.md` para el análisis completo. No es
   que nadie haya pensado en modelos mejores: el proyecto hermano (`RECUPERACION-ia-imagenes.md`)
   ya los probó en hardware similar y confirmó que son mucho más lentos en CPU.
4. **`steps`/`guidance_scale` hardcodeados en el frontend** (50 / 7.5) aunque la API los acepta
   como parámetros. No es un olvido documentado como bug — simplemente nadie construyó la UI
   para exponerlos todavía.
5. **Upscaler clásico (FSRCNN), no generativo.** Real-ESRGAN se descartó por conflictos de
   dependencias (`basicsr`/`torchvision`), ver lección aprendida #6 en `CLAUDE.md`.

## Hardware de referencia

**Confirmado por consulta directa al sistema (2026-09-07, no inferido):** Intel Core Ultra 5
135U, 12 núcleos/14 hilos, ~32GB RAM, Intel Graphics integrada (**sin GPU dedicada**), Windows
11 Pro. Coincide con lo documentado en `RECUPERACION-ia-imagenes.md` para el proyecto hermano.
**Disco: solo ~15.9GB libres de 475GB** tras montar el entorno de imágenes — la máquina ya está
mayormente ocupada por otras cosas; ten esto en cuenta antes de instalar modelos grandes
(SDXL/FLUX no caben con margen de seguridad hoy).

## Veredicto de recursos locales (2026-09-07)

Se benchmarkeó CPU vs. iGPU Intel (`GENERATIVA_IMAGE_DEVICE=GPU`, vía OpenVINO) generando la
misma imagen a 50 pasos (config de producción): **CPU 867s (14:27) vs. iGPU 128s (2:08) — 6.8x
más rápido, sin pérdida de calidad observable.** Ya aplicado como default en `start-dev.ps1`.
Con esto, el problema de velocidad/usabilidad está resuelto gratis en local. El techo de
calidad (SDXL/FLUX/ControlNet) sigue sin resolverse — no por falta de intento, sino por límite
real de disco y de la iGPU de este chip de bajo consumo. Ver el detalle completo y la tabla de
tiempos en [`docs/CAPACIDADES.md`](./docs/CAPACIDADES.md#veredicto-recursos-locales-medido-en-esta-máquina-2026-09-07).
Siguiente palanca legítima: GPU dedicada, local o en Azure/AWS.

## Estado del proyecto (a la fecha de este documento)

- ✅ Chat, generación de imágenes, edición (img2img), face-swap, escalado a Full HD —
  funcionando end-to-end.
- ✅ Instalador (Inno Setup) compilando con todos los modelos incluidos.
- ⏳ Pendiente: validar el instalador en una máquina limpia distinta (ThinkPad sin GPU
  dedicada, según nota en `CLAUDE.md`).
- ⬜ Video: descartado por hardware, pendiente de GPU NVIDIA.
- ⬜ `steps`/`guidance_scale`/`seed` no expuestos en la UI (solo vía API directa).
- ⬜ Sin guardado/historial/export de resultados, sin tests, sin cola de peticiones concurrentes,
  sin auth/multi-usuario — evaluación completa de estos huecos en
  `docs/EVALUACION-PRODUCTO.md`. Esto es lo que separa a "funciona para mí" de "listo para
  equipo o mercado".

## Gotchas de entorno ya resueltos (no volver a debuggear desde cero)

Lista completa en la sección "Lecciones aprendidas" de `CLAUDE.md`. Los más propensos a
reaparecer si se toca el entorno Python:
- `llama-cpp-python` no compila con MSVC en Windows → usar wheel precompilada CPU.
- Pin de versiones `openvino<2026` + `nncf==2.14.1` (conflicto con `optimum-intel`).
- Red corporativa con inspección TLS → `pip-system-certs` o falla `SSLCertVerificationError`
  al descargar de Hugging Face.
- Procesos en segundo plano lanzados por Claude Code mueren solos entre turnos en este entorno
  — no es bug del proyecto, reinicia el servicio.

## Si necesitas retomar trabajo activo

1. Confirma que el repo local sigue en `C:\jfrodriguezv\SourceCodeAnthropic\Personal\Generator`
   y que `git status` está limpio (o revisa qué cambios locales hay antes de asumir nada).
2. Sigue `README.md` para levantar los 4 servicios.
3. Si vas a tocar calidad de imagen/video, lee `docs/CAPACIDADES.md` primero — ya tiene la
   respuesta a "¿podemos subir la calidad?" con las opciones reales y su costo.
4. Si vas a tocar la API o el frontend, `docs/API.md` tiene el contrato exacto endpoint por
   endpoint, incluyendo qué hardcodea el frontend hoy.

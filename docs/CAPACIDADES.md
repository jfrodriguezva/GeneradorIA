# Capacidades reales: ¿qué tan alta es la calidad?

Respuesta corta: **razonable para fotorrealismo básico, lejos del estado del arte actual, y
video no existe**. Esto no es un bug ni algo a medio hacer — es el techo que impone el modelo
(SD1.5), no el hardware — la iGPU de esta máquina ya resuelve el problema de velocidad (ver
veredicto abajo). Este documento explica el porqué con detalle, para no repetir la pregunta ni
la investigación en el futuro.

## Veredicto: recursos locales, medido en esta máquina (2026-09-07)

Se benchmarkeó en la máquina real de desarrollo (**Intel Core Ultra 5 135U, 12C/14H, 32GB RAM,
sin GPU dedicada** — confirmado por consulta directa al sistema, no inferido) generando la
misma imagen (retrato, 512×768) en CPU vs. la iGPU Intel vía OpenVINO
(`GENERATIVA_IMAGE_DEVICE=GPU`):

| Pasos | CPU | iGPU Intel | Speedup |
|---|---|---|---|
| 20 | 285.5 s (4:46) | 93.2 s (1:33) | 3.1x |
| 50 (default de producción) | **867.3 s (14:27)** — medido, no estimado | **127.7 s (2:08)** — medido, no estimado | **6.8x** |

**Veredicto: el problema de velocidad/usabilidad está resuelto, gratis, con recursos 100%
locales.** Cambiar `GENERATIVA_IMAGE_DEVICE` de `CPU` a `GPU` (ya soportado en el código, solo
nadie lo había probado) baja una generación de producción de ~14.5 min a ~2 min, sin pérdida de
calidad observable en las muestras generadas (anatomía correcta, incluyendo manos/brazos
cruzados — el punto típico de falla de SD1.5). Ya aplicado como default en `start-dev.ps1`.

**Lo que NO se resuelve así — el techo de calidad (SDXL/FLUX/ControlNet) sigue igual de lejos,**
y no es solo cuestión de paciencia: al intentar dejar espacio para probar un modelo más grande
(SDXL), el setup de SD1.5 por sí solo (venv + modelo convertido + caché) consumió ~18GB, dejando
esta máquina en **15.9GB libres de 475GB totales** — es decir, el disco de esta máquina ya está
mayormente ocupado por otras cosas, no solo por este proyecto. Con ese margen no es prudente
intentar SDXL (checkpoint ~7GB + conversión a IR puede sumar 15-20GB más) sin arriesgar quedarse
sin espacio a medio proceso. Y aunque hubiera espacio, la iGPU de un chip de la serie U (bajo
consumo, sin VRAM dedicada, comparte los 32GB de RAM del sistema) probablemente no sostendría
SDXL en tiempos razonables — es una categoría de cómputo distinta a SD1.5.

**Conclusión**: se agotó lo que se podía optimizar gratis y en local. La velocidad ya no es el
problema. El techo de calidad sí sigue siendo un problema real, y la siguiente palanca legítima
es GPU dedicada — local (comprar hardware) o en la nube (Azure/AWS, ver conversación). No hay
más margen "gratis" que exprimir en esta máquina para subir la calidad del modelo.

## Prueba de estrés: dónde está el techo real (2026-09-07)

Con el worker real (`worker-python/image/main.py`, no un script aparte) corriendo en la iGPU,
se generó a propósito una escena diseñada para atacar los puntos débiles conocidos de SD1.5 a
la vez: dos personas interactuando con un choque de manos/dedos entrelazados, una con un reloj
de pulsera con números legibles, un café con latte art, y un espejo grande reflejando la calle
detrás — 60 pasos, 768×768, `guidance_scale=8.5`, sin upscale (falta el modelo FSRCNN).

**Tiempo: 313 s (5:13)** — sigue siendo "tiempo de café" incluso en una escena mucho más
compleja que un retrato simple.

**Qué logró bien:**
- Dos personas coherentes, rostros limpios, **sin errores de anatomía** (sin dedos extra, sin
  manos fusionadas) — el punto donde más suele fallar SD1.5.
- Texturas de tela convincentes (punto de suéter, brillo metálico, pliegues), piel con textura
  natural, iluminación cálida bien resuelta.

**Dónde falló — exactamente donde se esperaba, y de forma silenciosa (no con error):**
- **El choque de manos/dedos entrelazados pedido no ocurrió.** El modelo lo sustituyó por una
  pose más "cómoda" de su distribución de entrenamiento (una mano en el cabello) sin avisar.
- **El reloj no tiene números legibles** — esfera oscura genérica. Confirma: SD1.5 no puede
  renderizar texto/números, ni con prompt explícito.
- **El espejo refleja algo físicamente inconsistente** — una figura parcial que no corresponde
  exactamente a ninguna de las dos personas reales, y no refleja "la calle" pedida.
- **Sin latte art** — detalle fino específico perdido.

**Por qué importa esto más que "más nítido"**: la brecha real frente a SDXL/FLUX no es
resolución, es **seguir instrucciones complejas sin regresar silenciosamente a la pose/objeto
más común de su entrenamiento**. Eso es justo lo que arreglan los modelos más nuevos (mejor
seguimiento de prompt) y lo que ControlNet resuelve de raíz para interacciones físicas
específicas (posar manos exactamente donde se pide, en vez de dejarlo a la suerte del modelo).

## Imágenes

### Qué usa hoy

- **Modelo**: `SG161222/Realistic_Vision_V5.1_noVAE`, arquitectura **Stable Diffusion 1.5**
  (2022). No es SDXL, no es FLUX, no es Qwen-Image — todos ellos muy superiores en coherencia,
  composición, texto legible dentro de la imagen y anatomía.
- **Resolución nativa**: 512×768 (o los presets del frontend: 512×896 cuerpo completo, 768×768
  cuadrado, 896×512 horizontal). El "Full HD" es un upscaler clásico (FSRCNN x4 + recorte a
  1920px), no un modelo generativo que invente detalle nuevo — sube nitidez, no calidad de
  composición.
- **Parámetros por defecto** (`GenerateRequest`/`EditRequest` en `worker-python/image/main.py`):
  `steps=50`, `guidance_scale=7.5`, scheduler `DPMSolverMultistepScheduler` (DPM++, forzado en
  el pipeline). El frontend (`frontend-nextjs/src/app/imagenes/page.tsx`) **hardcodea**
  `steps: 50, guidanceScale: 7.5` — el usuario no puede subir/bajar esto desde la UI aunque la
  API sí lo acepta.
- El worker le agrega automáticamente a todo prompt un sufijo de calidad
  (`", professional photography, ultra detailed, sharp focus, high quality, 8k uhd, natural
  lighting"`) y, si no mandas negative prompt, usa uno por defecto orientado a evitar
  deformaciones/artefactos típicos de SD1.5 (manos, anatomía).
- **Tiempo**: 8-14 min por imagen a 20-30 pasos, 15-20 min a 50-60 pasos — **en CPU**. En la
  iGPU Intel (`GENERATIVA_IMAGE_DEVICE=GPU`), medido en esta máquina: ~2 min a 50 pasos (ver
  veredicto arriba). El instalador y la documentación original asumían solo CPU; ya no es el
  caso en hardware con iGPU Intel razonable.

### Por qué no es SDXL/FLUX/Qwen-Image

No es una omisión — ya se evaluó en un proyecto hermano en el mismo tipo de hardware (ver
`RECUPERACION-ia-imagenes.md`, notas de un portal ComfyUI separado que corrió en Intel Core
Ultra 5 135U / 32GB RAM / sin GPU dedicada). Ahí se llegaron a descargar y probar SDXL base
1.0 (6.9GB) y Qwen-Image-Edit (GGUF, ~12GB + text encoders). Esos modelos dan mucha mejor
calidad, pero:
- Son 3-10x más pesados en RAM/cómputo que SD1.5.
- En CPU, los tiempos por imagen suben a rangos de **decenas de minutos a horas** para edición.
- `Generativa` (este proyecto) prioriza **plomería funcional y consistente** sobre calidad
  máxima; SD1.5 fue una elección deliberada de compromiso velocidad/calidad para CPU-only.

### Cómo subir la calidad real (en orden de impacto)

1. **GPU dedicada NVIDIA (mínimo 8GB VRAM)** — el cambio de mayor impacto real en *calidad*.
   Permitiría migrar a SDXL o FLUX.1 manteniendo tiempos razonables. Esta es la única palanca
   que queda tras agotar las opciones locales gratis (ver veredicto arriba) — de aquí en
   adelante es hardware propio o nube (Azure/AWS).
2. **Subir `steps` más allá de 50-60** tiene rendimientos decrecientes en SD1.5 — no es la
   palanca correcta; el techo de calidad lo pone el modelo, no los pasos.
3. **Exponer `steps`/`guidance_scale`/`seed` en la UI** (hoy hardcodeados) — no mejora el techo
   de calidad, pero permite iterar/afinar sin tocar código.
4. ~~Probar `GENERATIVA_IMAGE_DEVICE=GPU`~~ — **ya probado y confirmado**: 6.8x más rápido en
   la iGPU Intel de esta máquina, sin pérdida de calidad observable. Mejora velocidad, no el
   techo de calidad del modelo. Ver veredicto arriba.

## Video

**No implementado, a propósito.** Ver `CLAUDE.md` sección "Video". Se pidió por el usuario,
se evaluó, se descartó explícitamente: un solo frame ya tarda minutos en CPU, un clip de 30s
tardaría horas o días — no es viable así. El proyecto hermano (ComfyUI) sí llegó a dejar
código listo para LTX-Video (modelo de 4.5GB, `ltxv-2b-0.9.8-distilled-fp8`) pero **sin probar
end-to-end** antes de borrarse.

Camino a habilitarlo: requiere GPU NVIDIA dedicada (mínimo 8GB VRAM, idealmente 12GB+). Con eso,
LTX-Video o modelos equivalentes (Wan, etc.) vía ComfyUI son la ruta más directa — no arrancar
esto sin confirmar que el hardware destino tiene GPU real.

## Face-swap

Este sí es rápido y de calidad aceptable independientemente del hardware: InsightFace
(`buffalo_l`) + `inswapper_128.onnx` corren en segundos vía onnxruntime, porque es una red
pequeña especializada, no un modelo generativo completo. No se beneficia mucho de más cómputo —
la calidad del resultado depende más de la resolución/ángulo de las fotos de entrada que del
modelo en sí.

## Resumen

| Aspecto | Estado actual | Techo real | Qué falta para subirlo |
|---|---|---|---|
| Generación de imagen | SD1.5, 512×768, ~2 min en iGPU (medido) | Medio (no SOTA) | GPU dedicada → SDXL/FLUX |
| Edición de imagen | Igual que arriba (img2img) | Medio | Igual |
| Face-swap | Rápido, calidad aceptable | Ya cerca de su techo | Poco margen de mejora |
| Escalado | Upscaler clásico (FSRCNN) | Nitidez, no detalle nuevo | Un upscaler generativo (Real-ESRGAN u otro) — descartado antes por conflictos de dependencias, ver `CLAUDE.md` |
| Video | No implementado | — | GPU NVIDIA dedicada (8GB+ VRAM) |

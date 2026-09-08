# Evaluación de producto: ¿qué tan funcional es esto en el mercado?

Evaluación desde cuatro ángulos: fotografía/edición, ingeniería de software, diseño UI/UX, e
integración de sistemas con equipos. Basada en el código real del repo (no en la intención de
diseño) — ver referencias de archivo en cada sección.

**Veredicto general: es una herramienta personal sólida, no un producto listo para mercado ni
para uso en equipo.** Cumple bien su objetivo original (validar la plomería de IA local sin
GPU), pero hay una distancia real entre "funciona para mí" y "es vendible / usable por otros".

---

## 1. Como herramienta fotográfica / de edición de imagen

**Nivel: entrada/aficionado, no profesional.**

Lo que tiene a favor:
- Fotorrealismo aceptable para uso casual (retratos, escenas simples) gracias al sufijo de
  calidad y negative prompt que el worker inyecta automáticamente (`worker-python/image/main.py`).
- Face-swap rápido (segundos) y de calidad razonable — la parte más madura del conjunto.
- Cuatro encuadres preconfigurados (retrato, cuerpo completo, cuadrado, horizontal).

Lo que le falta frente a herramientas de mercado (Midjourney, Adobe Firefly, Leonardo.Ai,
ComfyUI/Automatic1111 con SDXL/FLUX):
- **Resolución nativa 512×768** — una generación de 2022. El upscaler (FSRCNN) sube nitidez,
  no inventa detalle ni corrige composición; no es comparable a un upscaler generativo.
- **Sin control de composición/pose** (no hay ControlNet, IP-Adapter, regional prompting,
  inpainting/outpainting con máscara). Todo el control es vía texto — mismo techo que
  cualquier SD1.5 básico.
- **Sin consistencia de personaje/identidad** entre generaciones (no hay LoRA ni embeddings
  entrenables) — cada imagen es independiente, no puedes generar "el mismo personaje" en
  distintas poses de forma confiable.
- **Sin batch, sin variaciones, sin historial visual** — ver sección UX.
- Detalle completo del análisis de calidad en [`CAPACIDADES.md`](./CAPACIDADES.md).

**Para qué sí sirve hoy:** explorar ideas, generar assets casuales, probar face-swap rápido.
**Para qué no sirve todavía:** producción fotográfica profesional, campañas de marketing,
consistencia de marca/personaje, print de alta resolución.

## 2. Como pieza de ingeniería de software

**Nivel: prototipo funcional bien estructurado, sin higiene de producto.**

A favor:
- Separación de responsabilidades limpia (WPF orquesta, API C# es proxy puro, cada worker
  Python vive en su propio venv) — fácil de razonar y de reiniciar componentes sueltos.
- Health-checks antes de lanzar cada servicio (`ServiceOrchestrator.cs`).
- Lecciones de entorno bien documentadas (`CLAUDE.md`) — señal de mantenimiento cuidadoso, no
  de código tirado.

Ausente, y esto sí importa para "producto":
- **Cero tests** (`grep` de archivos `*test*` en todo el repo: ninguno). Nada de unit, nada de
  integración, nada de smoke test del pipeline completo.
- **Sin logging estructurado** en la API C# (no hay `ILogger`/Serilog configurado más allá de
  lo mínimo de ASP.NET) — depurar un fallo en producción sería mirar consola a ojo.
- **Sin cola/semáforo para las peticiones al worker de imágenes** — nada en
  `worker-python/image/main.py` serializa o limita generaciones concurrentes. Dos personas (o
  dos pestañas) generando a la vez compiten por el mismo CPU sin coordinación, con degradación
  de tiempos ya de por sí largos (8-20 min).
- **Sin persistencia**: ninguna imagen generada se guarda en disco ni hay base de datos/registro
  de qué se generó, cuándo, con qué prompt.
- **Sin CI/CD, sin versionado semántico, sin changelog.**
- Empaquetado solo para Windows (Inno Setup); no hay ruta a macOS/Linux.

## 3. Como diseño UI/UX

**Nivel: interfaz funcional mínima, sin trabajo de producto.**

Estado real (`frontend-nextjs/src/app`): 2 páginas (Chat, Imágenes), navegación de 2 links en
un `<nav>` con estilos inline, sin framework de diseño (no Tailwind, no librería de
componentes — solo `next`/`react` puros en `package.json`), tema oscuro fijo (sin toggle,
aunque tampoco hay claro que lo necesite).

Huecos concretos, verificados en el código:
- **No hay forma de guardar o descargar el resultado** — no existe ni un `<a download>` ni un
  botón de exportar en `imagenes/page.tsx`. El usuario tendría que hacer clic derecho →
  "guardar imagen como" sobre un `<img>` con `src` en base64.
- **No hay historial ni galería** — cada generación reemplaza a la anterior en el estado de
  React; al navegar o refrescar, se pierde.
- **Sin feedback de progreso real** durante los 8-20 minutos de espera (más allá de un estado
  de carga binario, a juzgar por la ausencia de barra de progreso/streaming de estado) — una
  espera tan larga sin señal intermedia es un problema de UX serio, no cosmético.
- **`steps`/`guidance_scale`/`seed` no son ajustables desde la UI** aunque la API los acepta
  (ver [`API.md`](./API.md)) — usuarios avanzados no tienen dónde afinar resultados sin llamar
  la API a mano.
- Sin responsive/mobile: estilos inline con valores fijos, pensado solo para escritorio.

## 4. Como sistema para integrar con equipos/personal

**Nivel: mono-usuario, mono-máquina. No está diseñado para equipo.**

- **Sin autenticación ni autorización** en ninguna capa (`api-csharp` no tiene
  `Authorize`/`Authentication` configurado) — aceptable porque todo escucha en
  `localhost`/`127.0.0.1` con CORS restringido, pero significa que **no hay forma de exponerlo
  en red y compartirlo con un equipo sin antes construir una capa de auth entera**.
- **Sin roles, sin multi-usuario, sin cuotas** — no hay concepto de "quién generó qué" ni
  límites por persona.
- **Sin API keys ni mecanismo de integración externa** (Zapier/n8n/webhooks) — los endpoints
  existen y son HTTP simples (ver `API.md`), así que técnicamente son automatizables, pero no
  hay nada pensado para eso (sin rate limiting, sin idempotencia, sin webhooks de finalización
  — el cliente tiene que hacer polling o esperar la respuesta síncrona 8-20 min).
- **Instalación por máquina**: cada persona necesita su propia instalación completa
  (Python, Node, .NET, ~5-7GB de modelos) vía el instalador Inno Setup — no hay modo
  cliente-servidor donde una máquina potente sirva a varias personas.
- Licencia del modelo de imagen (`Realistic_Vision_V5.1_noVAE`, derivado de SD1.5) no está
  verificada en este repo — antes de cualquier uso comercial o distribución a un equipo, hay
  que confirmar los términos de licencia del checkpoint en su fuente (Hugging Face/CivitAI),
  no asumirlos.

---

## Comparación honesta con el mercado

Frente a herramientas comerciales/consolidadas (Midjourney, Adobe Firefly, RunwayML,
Leonardo.Ai) o incluso frente a un ComfyUI/Automatic1111 bien configurado con SDXL/FLUX en
GPU: *Generativa* está por debajo en calidad de imagen, velocidad, control creativo y
madurez de producto (sin historial, sin export, sin multi-usuario). Su única ventaja
diferencial real es **100% local, sin API keys, sin costo recurrente, sin GPU** — un nicho
legítimo (privacidad, uso offline, sin suscripción) pero estrecho, y ese nicho no compite en
"máxima calidad", compite en "no depender de nada externo".

## Si el objetivo fuera llevarlo a producto/equipo (roadmap orientativo)

1. Guardado/historial de resultados con metadata (prompt, seed, parámetros) — el hueco más
   barato de cerrar y el que más impacto tiene en usabilidad real.
2. Cola de trabajos para el worker de imágenes (evita contención, permite mostrar progreso).
3. Exponer `steps`/`guidance_scale`/`seed` en la UI.
4. Tests mínimos de humo (levantar los 4 servicios, pegarle a cada endpoint, validar 200).
5. Decidir intencionalmente: ¿sigue siendo herramienta personal, o se vuelve cliente-servidor
   con auth para varias personas? Son dos productos distintos — no intentar ambos a medias.
6. Solo si hay GPU dedicada disponible: subir a SDXL/FLUX (ver `CAPACIDADES.md`) antes de
   invertir en las mejoras de arriba, porque el techo de calidad de imagen es la limitante más
   visible para cualquier audiencia externa.

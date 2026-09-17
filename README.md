# Generativa

Suite de IA generativa **100% local** (sin servicios externos, sin API keys, sin conexión a
internet salvo la primera vez que descarga modelos): chat, generación de imágenes, edición de
imágenes y face-swap. Pensada para correr en una PC **sin GPU dedicada** (todo vía CPU).

## ¿Qué hace?

| Función | Qué es |
|---|---|
| 💬 Chat | Conversación con un modelo de lenguaje local (Qwen2.5-3B) |
| 🖼️ Generar imágenes | Texto → imagen fotorrealista (Stable Diffusion 1.5) |
| ✏️ Editar imágenes | Imagen + texto → imagen modificada (img2img) |
| 🔁 Face-swap | Reemplaza el rostro de una persona en una foto por el de otra |
| 🔍 Escalado | Sube la resolución del resultado a Full HD |

Todo corre en tu máquina: no se sube ninguna imagen ni texto a internet, no hace falta API key
de OpenAI/Anthropic/etc.

**Nota:** no tiene filtro de contenido activado (decisión intencional, uso personal). El
contenido ilegal (menores, imágenes íntimas no consentidas de personas reales, etc.) sigue
siendo ilegal generarlo, filtro técnico o no.

## Cómo está armado (por si algo falla y quieres saber dónde mirar)

```
Generativa.Host.exe (app de escritorio, Windows)
  └─ abre una ventana que muestra el frontend web
  └─ enciende y vigila los 4 servicios de abajo

Frontend (Next.js, http://localhost:20001)  →  lo que ves en pantalla
  └─ le pide cosas a...

API (C#/.NET, puerto 20000)  →  solo reenvía pedidos, no piensa nada
  └─ le pide cosas a...

Worker de chat (Python, puerto 8011)     →  el modelo de lenguaje
Worker de imágenes (Python, puerto 8002) →  generación, edición, face-swap, escalado
```

Cada worker Python tiene su propio entorno virtual porque usan librerías pesadas distintas.

## Requisitos (una sola vez)

Instala esto si no lo tienes:

- **Python 3.12+** — https://www.python.org/downloads/ (marca "Add to PATH" al instalar)
- **Node.js LTS** — https://nodejs.org/
- **.NET SDK 10** — https://dotnet.microsoft.com/download

Verifica que están en el PATH:

```powershell
python --version
node --version
dotnet --version
```

## Primera vez: preparar el entorno

### 1. Crear los entornos virtuales de Python e instalar dependencias

```powershell
cd worker-python

# Entorno del chat
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r chat\requirements.txt

# Entorno de imágenes
python -m venv .venv-image
.\.venv-image\Scripts\python.exe -m pip install --upgrade pip
.\.venv-image\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.\.venv-image\Scripts\python.exe -m pip install -r image\requirements.txt
# controlnet_aux trae opencv-python-headless, que no debe coexistir con
# opencv-contrib-python-headless (dnn_superres, usado por el escalado, solo está en
# "contrib") -- reinstala el correcto al final:
.\.venv-image\Scripts\python.exe -m pip install --force-reinstall --no-deps opencv-contrib-python-headless
```

> ⚠️ No uses `pip install llama-cpp-python` a secas ni te saltes el `--extra-index-url`: sin la
> wheel precompilada intenta compilar desde código fuente y falla en Windows sin las
> herramientas de compilación de C++ instaladas.

### 2. Modelos

- **Chat (Qwen2.5-3B-Instruct GGUF, ~2GB)**: descárgalo y colócalo en
  `worker-python\models\qwen2.5-3b-instruct-q4_k_m.gguf` (crea la carpeta `models` si no
  existe). _(Pendiente: pega aquí el enlace de descarga que estés usando — no venía
  documentado en el repo)._
- **Imágenes (epiCRealism)**: no requiere descarga manual — la primera vez que
  generes una imagen, el worker la descarga desde Hugging Face y la convierte a formato
  OpenVINO automáticamente (tarda varios minutos, solo la primera vez; necesita internet en
  ese momento).
- **Face-swap (`inswapper_128.onnx`)**: colócalo en `worker-python\faceswap-models\`. Sin este
  archivo, el face-swap devuelve error 503 pero el resto de funciones sigue funcionando.
- **Restauración facial post face-swap (`GFPGANv1.4.pth`, opcional)**: colócalo también en
  `worker-python\faceswap-models\`. Sin este archivo, el face-swap sigue funcionando igual, solo
  que sin el paso de restauración (el rostro se nota más "pegado").
- **Escalado (`FSRCNN_x4.pb`)**: colócalo en `worker-python\upscale-models\`.
- **ControlNet, IP-Adapter, segmentación**: se descargan solos de Hugging Face la primera vez que
  se usa cada función (igual que el modelo de imágenes), no requieren descarga manual.

### 3. Dependencias del frontend

```powershell
cd frontend-nextjs
npm install
```

## Cómo levantar el proyecto en desarrollo

Con el entorno ya preparado (paso anterior, solo hace falta una vez), levantar todo es un solo
comando:

```powershell
powershell -File start-dev.ps1
```

Esto abre 4 ventanas de PowerShell (worker chat, worker imágenes, API, frontend). Espera a que
las 4 digan que están listas y luego abre **http://localhost:20001** en el navegador — ya puedes
usarlo así, sin necesidad de la app de escritorio.

Si además quieres probar la app de escritorio (WPF):

```powershell
cd host-wpf\Generativa.Host
dotnet run
```

(El host WPF hace health-check de los 4 servicios al arrancar y los lanza solo si no están ya
corriendo, así que también puedes saltarte `start-dev.ps1` y simplemente correr esto.)

## Puertos usados

| Servicio | Puerto |
|---|---|
| Frontend (Next.js) | 20001 |
| API (C#) | 20000 |
| Worker chat | 8011 |
| Worker imágenes | 8002 |

## Problemas comunes

- **El worker de imágenes tarda mucho**: es esperado, 8-14 min por imagen en CPU sin GPU
  dedicada (60 pasos puede llegar a 15-20 min). No es un cuelgue.
- **Un servicio no responde / se cerró solo**: reinícialo, no hace falta reiniciar los demás.
- **Face-swap da error 503**: falta el archivo `inswapper_128.onnx` en `worker-python\faceswap-models\`.
- **Error de certificados TLS al descargar modelos** (típico en redes corporativas): instala
  `pip-system-certs` en el venv correspondiente — ya está en `image\requirements.txt`, pero si
  pasa en el venv de chat instálalo ahí también.

Más detalle técnico (arquitectura completa, decisiones de diseño, lecciones de debugging,
instrucciones del instalador) está en [`CLAUDE.md`](./CLAUDE.md).

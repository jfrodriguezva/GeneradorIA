# Arranca los 3 servicios de desarrollo en ventanas separadas: worker Python, API C#, frontend Next.js.
# El host WPF se ejecuta aparte (dotnet run en host-wpf/Generativa.Host) una vez que los 3 estén arriba.

$root = $PSScriptRoot

$modelPath = Join-Path $root "worker-python\models\qwen2.5-3b-instruct-q4_k_m.gguf"

Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  "cd '$root\worker-python'; `$env:GENERATIVA_MODEL_PATH='$modelPath'; .\.venv\Scripts\python.exe chat\main.py"
)

Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  # De vuelta a CPU (era GPU): la iGPU Intel via OpenVINO es 6.8x mas rapida en /generate
  # (867s -> 128s a 50 pasos, ver docs/CAPACIDADES.md), pero /inpaint crashea el plugin GPU
  # (clWaitForEvents/CL_OUT_OF_RESOURCES, ver leccion aprendida #14 en CLAUDE.md) y deja el
  # contexto de la GPU corrupto para el resto del proceso. Mejor lento que roto -- cambiar a
  # GPU manualmente solo si vas a usar unicamente /generate en esa sesion.
  "cd '$root\worker-python'; `$env:GENERATIVA_IMAGE_DEVICE='CPU'; .\.venv-image\Scripts\python.exe image\main.py"
)

Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  "cd '$root\api-csharp\Generativa.Api'; dotnet run"
)

Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  "cd '$root\frontend-nextjs'; npm run dev"
)

Write-Host "Servicios lanzados: worker chat (8011), worker imagenes (8002), API C# (20000), frontend Next.js (20001)."

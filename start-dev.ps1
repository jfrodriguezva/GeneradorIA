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
  # GPU = iGPU Intel vía OpenVINO. Medido en esta máquina (Core Ultra 5 135U): 6.8x más rápido
  # que CPU a 50 pasos (867s -> 128s) sin pérdida de calidad observada. Ver docs/CAPACIDADES.md.
  "cd '$root\worker-python'; `$env:GENERATIVA_IMAGE_DEVICE='GPU'; .\.venv-image\Scripts\python.exe image\main.py"
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

<#
.SYNOPSIS
    Levanta el entorno de desarrollo local usando Google Colab (GPU) como Worker de Imágenes remoto.

.EXAMPLE
    powershell -File start-dev-colab.ps1 -ColabUrl "https://xxxx-xx-xx.trycloudflare.com"
#>
param(
    [Parameter(Mandatory = $true, HelpMessage = "URL pública del túnel de Google Colab (ej. https://xxxx.trycloudflare.com)")]
    [string]$ColabUrl,

    [switch]$SkipChatWorker
)

$root = $PSScriptRoot
$cleanUrl = $ColabUrl.Trim().TrimEnd('/')

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Generativa — Modo Híbrido (Frontend/API Local + GPU Colab)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Verificando conexión con el Worker de Imágenes en Colab: $cleanUrl/health ..."

try {
    $headers = @{ "ngrok-skip-browser-warning" = "true" }
    $resp = Invoke-RestMethod -Uri "$cleanUrl/health" -Method Get -Headers $headers -TimeoutSec 15
    Write-Host "[OK] Worker en Colab respondió: status=$($resp.status), model_loaded=$($resp.model_loaded), device=$($resp.device)" -ForegroundColor Green
}
catch {
    Write-Warning "No se pudo verificar $cleanUrl/health todavía ($($_.Exception.Message)). Se continuará levantando los servicios."
}

if (-not $SkipChatWorker) {
    $modelPath = Join-Path $root "worker-python\models\qwen2.5-3b-instruct-q4_k_m.gguf"
    $venvChat = Join-Path $root "worker-python\.venv\Scripts\python.exe"
    if (Test-Path $venvChat) {
        Start-Process powershell -ArgumentList @(
            "-NoExit", "-Command",
            "cd '$root\worker-python'; `$env:GENERATIVA_MODEL_PATH='$modelPath'; .\.venv\Scripts\python.exe chat\main.py"
        )
    }
    else {
        Write-Warning "No se encontró worker-python\.venv — se omite el Worker de Chat local."
    }
}

# Levanta la API C# apuntando al túnel de Google Colab
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root\api-csharp\Generativa.Api'; `$env:GENERATIVA_IMAGE_WORKER_URL='$cleanUrl'; dotnet run"
)

# Levanta el Frontend Next.js
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root\frontend-nextjs'; npm run dev"
)

Write-Host ""
Write-Host "Servicios lanzados:" -ForegroundColor Green
Write-Host "  - Worker Imágenes (GPU Colab): $cleanUrl"
Write-Host "  - API C# (Proxy Local)       : http://localhost:20000"
Write-Host "  - Frontend Next.js           : http://localhost:20001/imagenes"

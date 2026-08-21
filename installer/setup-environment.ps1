#Requires -RunAsAdministrator
# Prepara el entorno de Generativa en una maquina nueva: instala Python y Node.js si faltan
# (via winget, siempre la ultima version estable), crea los entornos virtuales de Python,
# instala las dependencias de cada worker, y descarga node_modules del frontend si hace falta.
#
# Se ejecuta una sola vez, justo despues de que el instalador copia los archivos, con {app}
# como directorio de trabajo (este script vive en la raiz de la instalacion).

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$logPath = Join-Path $root "setup-environment.log"
Start-Transcript -Path $logPath -Append

function Refresh-Path {
    $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Ensure-Winget {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Host "ERROR: no se encontro 'winget' (App Installer) en este equipo."
        Write-Host "Instala Python 3.12+ y Node.js LTS manualmente desde python.org y nodejs.org,"
        Write-Host "luego vuelve a ejecutar este script."
        Stop-Transcript
        exit 1
    }
}

function Ensure-Python {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        Write-Host "Python ya esta instalado: $($python.Source)"
        return
    }
    Write-Host "Instalando Python (ultima version estable) con winget..."
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "No se pudo localizar python.exe despues de instalarlo. Puede requerir reiniciar sesion."
    }
    Write-Host "Python instalado: $($python.Source)"
}

function Ensure-NodeJs {
    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($node) {
        Write-Host "Node.js ya esta instalado: $($node.Source)"
        return
    }
    Write-Host "Instalando Node.js LTS con winget..."
    winget install --id OpenJS.NodeJS.LTS -e --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) {
        throw "No se pudo localizar node.exe despues de instalarlo. Puede requerir reiniciar sesion."
    }
    Write-Host "Node.js instalado: $($node.Source)"
}

function New-WorkerVenv([string]$venvDir, [string]$requirementsFile, [switch]$IsImageWorker) {
    if (Test-Path (Join-Path $venvDir "Scripts\python.exe")) {
        Write-Host "Entorno ya existe: $venvDir"
        return
    }
    Write-Host "Creando entorno virtual en $venvDir..."
    python -m venv $venvDir
    $venvPython = Join-Path $venvDir "Scripts\python.exe"

    & $venvPython -m pip install --upgrade pip --quiet

    if ($IsImageWorker) {
        Write-Host "Instalando PyTorch (CPU-only)..."
        & $venvPython -m pip install torch --index-url https://download.pytorch.org/whl/cpu --quiet
        Write-Host "Instalando pip-system-certs (compatibilidad con proxies corporativos)..."
        & $venvPython -m pip install pip-system-certs --quiet
        Write-Host "Instalando el resto de dependencias del worker de imagenes..."
        & $venvPython -m pip install -r $requirementsFile --quiet
    }
    else {
        Write-Host "Instalando llama-cpp-python (wheel precompilada CPU)..."
        & $venvPython -m pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu --quiet
        Write-Host "Instalando el resto de dependencias del worker de chat..."
        & $venvPython -m pip install fastapi uvicorn[standard] pydantic --quiet
    }
    Write-Host "Entorno listo: $venvDir"
}

function Ensure-FrontendDeps {
    $frontendDir = Join-Path $root "frontend-nextjs"
    if (Test-Path (Join-Path $frontendDir "node_modules")) {
        Write-Host "node_modules ya presente en el frontend, se omite npm install."
        return
    }
    Write-Host "Instalando dependencias del frontend (npm install)..."
    Push-Location $frontendDir
    npm install
    Pop-Location
}

Write-Host "=== Preparando entorno de Generativa ==="
Ensure-Winget
Ensure-Python
Ensure-NodeJs

New-WorkerVenv -venvDir (Join-Path $root "worker-python\.venv") -requirementsFile (Join-Path $root "worker-python\chat\requirements.txt")
New-WorkerVenv -venvDir (Join-Path $root "worker-python\.venv-image") -requirementsFile (Join-Path $root "worker-python\image\requirements.txt") -IsImageWorker
Ensure-FrontendDeps

Write-Host "=== Entorno listo. Ya puedes ejecutar Generativa.Host.exe ==="
Stop-Transcript

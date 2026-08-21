; Instalador de Generativa (suite de IA generativa local: chat, imágenes)
; Compilar con Inno Setup 6: ISCC.exe installer\generativa.iss
; Requiere que antes se hayan hecho:
;   - dotnet publish (Release, win-x64, self-contained) de host-wpf y api-csharp
;   - npm run build en frontend-nextjs
;   - los modelos ya descargados en worker-python/models y worker-python/image/ov-models
;
; Python y Node.js NO se empaquetan: el instalador los instala en la máquina destino
; (vía winget, siempre la última versión estable) durante el post-instalación, y ahí mismo
; crea los entornos virtuales de Python e instala sus dependencias. Ver setup-environment.ps1.

#define MyAppName "Generativa"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Generativa"
#define RepoRoot "..\"

[Setup]
AppId={{B6B2E6B6-6E8B-4B0B-9C7B-3B7B6C0F1A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=output
OutputBaseFilename=GenerativaSetup
Compression=lzma2/normal
SolidCompression=yes
DiskSpanning=yes
DiskSliceSize=max
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
; Host WPF (self-contained, single-file) va en la raíz de instalación.
Source: "{#RepoRoot}host-wpf\Generativa.Host\publish\*"; DestDir: "{app}"; Flags: ignoreversion

; API en C# (self-contained, single-file).
Source: "{#RepoRoot}api-csharp\Generativa.Api\publish\*"; DestDir: "{app}\api-csharp"; Flags: ignoreversion recursesubdirs createallsubdirs

; Workers de Python: solo código y requirements. Los entornos virtuales se crean en el
; equipo destino durante el post-instalación (no son portables entre máquinas).
Source: "{#RepoRoot}worker-python\chat\*"; DestDir: "{app}\worker-python\chat"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__"
Source: "{#RepoRoot}worker-python\image\main.py"; DestDir: "{app}\worker-python\image"; Flags: ignoreversion
Source: "{#RepoRoot}worker-python\image\faceswap.py"; DestDir: "{app}\worker-python\image"; Flags: ignoreversion
Source: "{#RepoRoot}worker-python\image\upscale.py"; DestDir: "{app}\worker-python\image"; Flags: ignoreversion
Source: "{#RepoRoot}worker-python\image\requirements.txt"; DestDir: "{app}\worker-python\image"; Flags: ignoreversion

; Script que instala Python/Node.js si faltan y arma los entornos virtuales.
Source: "setup-environment.ps1"; DestDir: "{app}"; Flags: ignoreversion

; Modelos ya descargados/convertidos (son datos, sí son portables entre máquinas).
Source: "{#RepoRoot}worker-python\models\*"; DestDir: "{app}\worker-python\models"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#RepoRoot}worker-python\image\ov-models\Realistic_Vision_V5.1_noVAE\*"; DestDir: "{app}\worker-python\image\ov-models\Realistic_Vision_V5.1_noVAE"; Flags: ignoreversion recursesubdirs createallsubdirs

; Modelos de face-swap (InsightFace buffalo_l + inswapper) y de escalado a Full HD.
Source: "{#RepoRoot}worker-python\faceswap-models\*"; DestDir: "{app}\worker-python\faceswap-models"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#RepoRoot}worker-python\upscale-models\*"; DestDir: "{app}\worker-python\upscale-models"; Flags: ignoreversion recursesubdirs createallsubdirs

; Frontend Next.js en modo producción (node_modules/.next son portables entre máquinas
; Windows x64 con la misma versión de Node; si algo no coincide, el script reinstala con npm).
; Se excluyen cache/dev porque son artefactos de "npm run dev" (no se necesitan para
; "next start" en producción) y a veces quedan con archivos bloqueados por el proceso.
Source: "{#RepoRoot}frontend-nextjs\.next\*"; DestDir: "{app}\frontend-nextjs\.next"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "cache\*,dev\*"
Source: "{#RepoRoot}frontend-nextjs\node_modules\*"; DestDir: "{app}\frontend-nextjs\node_modules"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#RepoRoot}frontend-nextjs\public\*"; DestDir: "{app}\frontend-nextjs\public"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#RepoRoot}frontend-nextjs\package.json"; DestDir: "{app}\frontend-nextjs"; Flags: ignoreversion
Source: "{#RepoRoot}frontend-nextjs\next.config.ts"; DestDir: "{app}\frontend-nextjs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\Generativa.Host.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Generativa.Host.exe"; Tasks: desktopicon

[Run]
; Se ejecuta en una consola visible (no silencioso) para que el usuario vea el progreso
; de instalar Python/Node.js y armar los entornos — puede tardar varios minutos.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup-environment.ps1"""; WorkingDir: "{app}"; StatusMsg: "Preparando Python, Node.js y los entornos virtuales (puede tardar varios minutos)..."; Flags: waituntilterminated
Filename: "{app}\Generativa.Host.exe"; Description: "Ejecutar {#MyAppName}"; Flags: nowait postinstall skipifsilent

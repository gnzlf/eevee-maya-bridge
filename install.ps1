param([string]$MayaVersion = '2024')
$ErrorActionPreference = 'Stop'
if ($MayaVersion -ne '2024') { throw 'Los binarios de esta version estan compilados para Maya 2024. Otros Maya requieren recompilar y validar el SDK correspondiente.' }
$projectPath = $PSScriptRoot
$mayaPath = Join-Path $env:ProgramFiles "Autodesk\Maya$MayaVersion\bin\maya.exe"
if (-not (Test-Path -LiteralPath $mayaPath)) { throw "Maya $MayaVersion no esta instalado." }
$config = Get-Content -LiteralPath (Join-Path $projectPath 'config.json') -Raw | ConvertFrom-Json
foreach ($library in @('eevee_gpu_v5.dll', 'eevee_scene.dll')) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectPath "bin\$library"))) { throw "Falta bin\$library. Compilar native con CMake antes de instalar." }
}
if (-not (Test-Path -LiteralPath $config.blender)) { throw 'Configura la ruta de Blender en config.json.' }
$moduleDirectory = Join-Path ([Environment]::GetFolderPath('MyDocuments')) "maya\$MayaVersion\modules"
New-Item -ItemType Directory -Force -Path $moduleDirectory | Out-Null
$moduleFile = Join-Path $moduleDirectory 'EeveeMayaBridge.mod'
$versionSource = Get-Content -LiteralPath (Join-Path $projectPath 'scripts\eevee_maya\__init__.py') -Raw
$bridgeVersion = [regex]::Match($versionSource,'__version__\s*=\s*"([0-9.]+)"').Groups[1].Value
if (-not $bridgeVersion) { throw 'No se pudo leer la version del puente.' }
$moduleContent = "+ MAYAVERSION:$MayaVersion PLATFORM:win64 EeveeMayaBridge $bridgeVersion $projectPath`r`n"
if ((Test-Path -LiteralPath $moduleFile) -and ((Get-Content -LiteralPath $moduleFile -Raw).Trim() -ne $moduleContent.Trim())) {
    Copy-Item -LiteralPath $moduleFile -Destination ($moduleFile + '.' + (Get-Date -Format yyyyMMddHHmmss) + '.bak')
}
Set-Content -LiteralPath $moduleFile -Value $moduleContent -Encoding UTF8
Write-Output "Modulo instalado: $moduleFile"
Write-Output 'En Maya: Plug-in Manager > eeveeBridge.py > Loaded y Auto load; despues menu Eevee.'

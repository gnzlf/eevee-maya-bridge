param([Parameter(Mandatory=$true)][ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version,
      [Parameter(Mandatory=$true)][string]$NotesFile,
      [string]$Python = 'python', [switch]$Draft)
$ErrorActionPreference = 'Stop'
$rootPath = Split-Path $PSScriptRoot
$config = Get-Content -LiteralPath (Join-Path $rootPath 'release-config.json') -Raw | ConvertFrom-Json
$source = Get-Content -LiteralPath (Join-Path $rootPath 'scripts\eevee_maya\__init__.py') -Raw
if ([regex]::Match($source,'__version__\s*=\s*"([0-9.]+)"').Groups[1].Value -ne $Version) { throw 'Primero actualiza __version__ en scripts/eevee_maya/__init__.py y confirma los cambios.' }
if (git -C $rootPath status --porcelain) { throw 'Hay cambios sin confirmar. Confirma y revisa el código antes de publicar.' }
& $Python (Join-Path $PSScriptRoot 'build_release.py')
if ($LASTEXITCODE -ne 0) { throw 'Falló el empaquetado.' }
git -c 'credential.helper=!gh auth git-credential' -C $rootPath push origin main
if ($LASTEXITCODE -ne 0) { throw 'Falló el push; no se publicó el release.' }
$tagName = 'v' + $Version
$assetPrefix = Join-Path $rootPath ('dist\EeveeMayaBridge-' + $Version + '-maya2024-win64')
$releaseArguments = @('release','create',$tagName,'--repo',$config.repository,'--target','main','--title',('Eevee Maya Bridge '+$Version),
    '--notes-file',$NotesFile,($assetPrefix+'-Setup.exe'),($assetPrefix+'.zip'),(Join-Path $rootPath 'dist\SHA256SUMS.txt'))
if ($Draft) { $releaseArguments += '--draft' }
gh @releaseArguments
if ($LASTEXITCODE -ne 0) { throw 'No se pudo publicar el release. No reemplaces artefactos de una versión ya publicada; incrementa la versión.' }

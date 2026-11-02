$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $root

function Invoke-Git([string[]] $Arguments) {
    & git -C $root @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Falló git $($Arguments -join ' ')" }
}

try {
    $sourcePath = Join-Path $root 'scripts\eevee_maya\__init__.py'
    $source = Get-Content -LiteralPath $sourcePath -Raw
    $match = [regex]::Match($source, '__version__\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"')
    if (-not $match.Success) { throw 'No se pudo leer __version__.' }
    $originalVersion = $match.Groups[1].Value
    $versionParts = [int[]]($originalVersion -split '\.')
    $notes = Join-Path $root 'release-notes.md'
    if (-not (Test-Path -LiteralPath $notes)) { throw 'Falta release-notes.md.' }

    $config = Get-Content -LiteralPath (Join-Path $root 'release-config.json') -Raw | ConvertFrom-Json
    $repo = [string]$config.repository

    while ($true) {
        $version = ($versionParts -join '.')
        $tag = 'v' + $version
        $null = & gh release view $tag --repo $repo 2>$null
        if ($LASTEXITCODE -ne 0) { break }
        $versionParts[2]++
    }
    $automaticBump = $version -ne $originalVersion

    $changes = @(git -C $root status --short)
    if ($changes.Count -eq 0 -and -not $automaticBump) { throw 'No hay cambios locales para publicar.' }

    Write-Host ''
    Write-Host "Version a publicar: $version" -ForegroundColor Cyan
    if ($automaticBump) {
        Write-Host "El release $originalVersion ya existe; se actualizara __version__ automaticamente." -ForegroundColor Yellow
    }
    Write-Host "Repositorio: $repo" -ForegroundColor Cyan
    Write-Host ''
    Write-Host 'Se incluiran estos cambios en el commit:' -ForegroundColor Yellow
    $changes | ForEach-Object { Write-Host "  $_" }
    Write-Host ''
    Write-Host 'El flujo compilara el ZIP y el instalador, hara push a main y creara el release.' -ForegroundColor Yellow
    $answer = Read-Host 'Escribe PUBLICAR para continuar'
    if ($answer -cne 'PUBLICAR') { Write-Host 'Cancelado.'; exit 1 }

    if ($automaticBump) {
        $start = $match.Groups[1].Index
        $length = $match.Groups[1].Length
        $source = $source.Substring(0, $start) + $version + $source.Substring($start + $length)
        [System.IO.File]::WriteAllText($sourcePath, $source, (New-Object System.Text.UTF8Encoding($false)))
    }

    Invoke-Git @('add', '--all')
    $staged = @(git -C $root diff --cached --name-only)
    if ($staged.Count -eq 0) { throw 'No quedaron cambios preparados para el commit.' }
    Invoke-Git @('commit', '-m', "Publicar Eevee Maya Bridge $version")

    & (Join-Path $root 'tools\publish_release.ps1') -Version $version -NotesFile $notes
    if ($LASTEXITCODE -ne 0) { throw 'Falló el flujo de compilación o publicación.' }

    Write-Host ''
    Write-Host "Publicado: https://github.com/$repo/releases/tag/$tag" -ForegroundColor Green
    exit 0
}
catch {
    Write-Host ''
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

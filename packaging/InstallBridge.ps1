param(
    [string]$PayloadPath,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'EeveeMayaBridge'),
    [string]$BlenderPath,
    [string]$ModuleDirectory,
    [switch]$SkipMayaCheck,
    [switch]$NoRegistration,
    [switch]$Uninstall
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Resolve-Full([string]$Path) { [IO.Path]::GetFullPath($Path) }
function Hash-File([string]$Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','') }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
function Remove-OwnedTree([string]$Path) {
    $targetPath = Resolve-Full $Path
    $rootPath = (Resolve-Full $InstallRoot).TrimEnd('\') + '\'
    if (-not $targetPath.StartsWith($rootPath, [StringComparison]::OrdinalIgnoreCase)) { throw 'Ruta fuera de la instalación' }
    if (Test-Path -LiteralPath $targetPath) { Remove-Item -LiteralPath $targetPath -Recurse -Force }
}
function Write-AtomicJson([string]$Path, $Value) {
    $temporaryPath = $Path + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    $Value | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $temporaryPath -Encoding UTF8
    if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($temporaryPath, $Path, [NullString]::Value) }
    else { [IO.File]::Move($temporaryPath, $Path) }
}
function Expand-VerifiedZip([string]$Archive, [string]$Destination) {
    $zipFile = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        $basePath = (Resolve-Full $Destination).TrimEnd('\') + '\'
        foreach ($entry in $zipFile.Entries) {
            $entryPath = Resolve-Full (Join-Path $Destination $entry.FullName)
            if (-not $entryPath.StartsWith($basePath, [StringComparison]::OrdinalIgnoreCase)) { throw 'ZIP con ruta no válida' }
            if (($entry.ExternalAttributes -band 0xF0000000) -eq 0xA0000000) { throw 'ZIP con enlace simbólico no admitido' }
        }
    } finally { $zipFile.Dispose() }
    [IO.Compression.ZipFile]::ExtractToDirectory($Archive, $Destination)
}
function Assert-Blender([string]$Executable) {
    if (-not (Test-Path -LiteralPath $Executable)) { return $false }
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $Executable; $info.Arguments = '--version'
    $info.UseShellExecute = $false; $info.CreateNoWindow = $true; $info.WindowStyle = 'Hidden'
    $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    $probe = [Diagnostics.Process]::Start($info)
    if (-not $probe.WaitForExit(15000)) { $probe.Kill(); return $false }
    $outputText = $probe.StandardOutput.ReadToEnd()
    return $probe.ExitCode -eq 0 -and $outputText -match '(?m)^Blender 5\.2\.'
}
function Download-File([string]$Url, [string]$Destination) {
    $client = [Net.WebClient]::new()
    try { $client.DownloadFile($Url, $Destination) } finally { $client.Dispose() }
}

$InstallRoot = Resolve-Full $InstallRoot
if ($Uninstall) {
    if (Get-Process -Name maya,blender -ErrorAction SilentlyContinue) { throw 'Cierra Maya y Blender antes de desinstalar.' }
    $statePath = Join-Path $InstallRoot 'installation.json'
    if (-not (Test-Path -LiteralPath $statePath)) { throw 'No se encontró esta instalación.' }
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $moduleFile = [string]$state.module_file
    if ((Test-Path -LiteralPath $moduleFile) -and (Get-Content -LiteralPath $moduleFile -Raw).Contains($InstallRoot)) {
        Remove-Item -LiteralPath $moduleFile
        $previousModule = Join-Path $InstallRoot 'module-before-install.mod'
        if (Test-Path -LiteralPath $previousModule) { Copy-Item -LiteralPath $previousModule -Destination $moduleFile }
    }
    foreach ($name in @('versions','runtime','downloads')) { Remove-OwnedTree (Join-Path $InstallRoot $name) }
    Remove-Item -LiteralPath $statePath
    $registryPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\EeveeMayaBridge'
    if (-not $NoRegistration -and $state.registered -and (Test-Path -LiteralPath $registryPath)) {
        if ((Get-ItemProperty -LiteralPath $registryPath).InstallLocation -eq $InstallRoot) { Remove-Item -LiteralPath $registryPath }
    }
    Write-Output 'Desinstalado. Se conservaron la configuración y el módulo anterior.'
    exit 0
}

Write-Output 'PROGRESS|5|Comprobando Maya 2024 y el paquete…'
$mayaExecutable = Join-Path $env:ProgramFiles 'Autodesk\Maya2024\bin\maya.exe'
if (-not (Test-Path -LiteralPath $mayaExecutable)) {
    $registryMaya = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Autodesk\Maya\2024\Setup\InstallPath' -ErrorAction SilentlyContinue
    if ($registryMaya.MAYA_INSTALL_LOCATION) { $mayaExecutable = Join-Path $registryMaya.MAYA_INSTALL_LOCATION 'bin\maya.exe' }
}
if (-not $SkipMayaCheck -and -not (Test-Path -LiteralPath $mayaExecutable)) { throw 'Se requiere Maya 2024 de 64 bits instalado. Maya no se incluye en este instalador.' }
if (-not $PayloadPath -or -not (Test-Path -LiteralPath $PayloadPath)) { throw 'Falta el paquete del puente.' }
New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
$workPath = Join-Path $InstallRoot ('staging-' + [guid]::NewGuid().ToString('N'))
try {
    Expand-VerifiedZip $PayloadPath $workPath
    $manifest = Get-Content -LiteralPath (Join-Path $workPath 'package.json') -Raw | ConvertFrom-Json
    $version = [string]$manifest.version
    if ($version -notmatch '^\d+\.\d+\.\d+$' -or $manifest.maya_version -ne '2024') { throw 'Versión o Maya del paquete no compatible.' }
    foreach ($item in $manifest.files.PSObject.Properties) {
        $filePath = Resolve-Full (Join-Path $workPath $item.Name)
        if (-not $filePath.StartsWith($workPath + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Manifiesto con ruta no válida.' }
        if ((Hash-File $filePath) -ne $item.Value) { throw ('Checksum incorrecto: ' + $item.Name) }
    }
    $release = Get-Content -LiteralPath (Join-Path $workPath 'release-config.json') -Raw | ConvertFrom-Json
    Write-Output 'PROGRESS|15|Preparando Blender 5.2 portátil…'
    $settingsPath = Join-Path $InstallRoot 'config.json'
    if (-not $BlenderPath -and (Test-Path -LiteralPath $settingsPath)) { $BlenderPath = (Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json).blender }
    if (-not $BlenderPath) { $BlenderPath = Join-Path $env:ProgramFiles 'Blender Foundation\Blender 5.2\blender.exe' }
    if (-not (Assert-Blender $BlenderPath)) {
        $runtimePath = Join-Path $InstallRoot ('runtime\blender-' + $release.blender_version + '-windows-x64')
        $BlenderPath = Join-Path $runtimePath 'blender.exe'
        if (-not (Assert-Blender $BlenderPath)) {
            $downloadsPath = Join-Path $InstallRoot 'downloads'
            New-Item -ItemType Directory -Path $downloadsPath -Force | Out-Null
            $archivePath = Join-Path $downloadsPath ('blender-' + $release.blender_version + '.zip')
            if (-not (Test-Path -LiteralPath $archivePath) -or (Hash-File $archivePath) -ne $release.blender_sha256) {
                Write-Output 'PROGRESS|20|Descargando Blender desde blender.org (aprox. 400 MB)…'
                Download-File $release.blender_url ($archivePath + '.part')
                if ((Hash-File ($archivePath + '.part')) -ne $release.blender_sha256) { throw 'El SHA-256 de Blender no coincide.' }
                Move-Item -LiteralPath ($archivePath + '.part') -Destination $archivePath -Force
            }
            Write-Output 'PROGRESS|50|Extrayendo Blender…'
            $runtimeStage = Join-Path $InstallRoot ('runtime-stage-' + [guid]::NewGuid().ToString('N'))
            try {
                Expand-VerifiedZip $archivePath $runtimeStage
                $expandedRuntime = Join-Path $runtimeStage ('blender-' + $release.blender_version + '-windows-x64')
                if (-not (Assert-Blender (Join-Path $expandedRuntime 'blender.exe'))) { throw 'Blender descargado no inicia correctamente.' }
                New-Item -ItemType Directory -Path (Split-Path $runtimePath) -Force | Out-Null
                if (Test-Path -LiteralPath $runtimePath) { throw 'Existe un runtime inválido. Revisa la carpeta runtime antes de reinstalar.' }
                Move-Item -LiteralPath $expandedRuntime -Destination $runtimePath
            } finally { Remove-OwnedTree $runtimeStage }
        }
    }
    Write-Output 'PROGRESS|75|Instalando el puente en una carpeta de versión independiente…'
    $versionsPath = Join-Path $InstallRoot 'versions'
    New-Item -ItemType Directory -Path $versionsPath -Force | Out-Null
    $versionPath = Join-Path $versionsPath $version
    if (Test-Path -LiteralPath $versionPath) {
        foreach ($item in $manifest.files.PSObject.Properties) {
            if ((Hash-File (Join-Path $versionPath $item.Name)) -ne $item.Value) { throw 'Esa versión ya existe con archivos distintos. Publica una versión nueva.' }
        }
    } else { Move-Item -LiteralPath $workPath -Destination $versionPath }
    $userSettings = if (Test-Path -LiteralPath $settingsPath) { Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json } else { [pscustomobject]@{} }
    $userSettings | Add-Member -MemberType NoteProperty -Name blender -Value $BlenderPath -Force
    Write-AtomicJson $settingsPath $userSettings
    if (-not $ModuleDirectory) { $ModuleDirectory = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'maya\2024\modules' }
    New-Item -ItemType Directory -Path $ModuleDirectory -Force | Out-Null
    $moduleFile = Join-Path $ModuleDirectory 'EeveeMayaBridge.mod'
    $backupPath = Join-Path $InstallRoot 'module-before-install.mod'
    if ((Test-Path -LiteralPath $moduleFile) -and -not (Test-Path -LiteralPath (Join-Path $InstallRoot 'installation.json')) -and -not (Test-Path -LiteralPath $backupPath)) {
        Copy-Item -LiteralPath $moduleFile -Destination $backupPath
    }
    $moduleText = "+ MAYAVERSION:2024 PLATFORM:win64 EeveeMayaBridge $version $versionPath`r`n"
    $moduleTemporary = $moduleFile + '.tmp'
    [IO.File]::WriteAllText($moduleTemporary, $moduleText, [Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $moduleFile) { [IO.File]::Replace($moduleTemporary, $moduleFile, [NullString]::Value) } else { [IO.File]::Move($moduleTemporary, $moduleFile) }
    Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $InstallRoot 'maintenance.ps1') -Force
    Write-AtomicJson (Join-Path $InstallRoot 'installation.json') ([ordered]@{version=$version;maya_version='2024';module_file=$moduleFile;version_path=$versionPath;blender=$BlenderPath;registered=(-not $NoRegistration)})
    if (-not $NoRegistration) {
        $registryPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\EeveeMayaBridge'
        New-Item -Path $registryPath -Force | Out-Null
        $uninstallCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $InstallRoot 'maintenance.ps1') + '" -Uninstall -InstallRoot "' + $InstallRoot + '"'
        foreach ($entry in @{DisplayName='Eevee Maya Bridge';DisplayVersion=$version;Publisher='Eevee Maya Bridge';InstallLocation=$InstallRoot;UninstallString=$uninstallCommand}.GetEnumerator()) {
            Set-ItemProperty -LiteralPath $registryPath -Name $entry.Key -Value $entry.Value
        }
    }
    Write-Output 'PROGRESS|100|Instalación completa. Reinicia Maya para activar esta versión.'
    Write-Output 'Primera instalación: carga eeveeBridge.py en Plug-in Manager y habilita Auto load si lo deseas.'
} finally { Remove-OwnedTree $workPath }

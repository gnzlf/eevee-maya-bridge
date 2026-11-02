@echo off
setlocal
title Eevee Maya Bridge - Publicar version
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\publicar_version_github.ps1"
set "exitCode=%ERRORLEVEL%"
echo.
if not "%exitCode%"=="0" echo La publicacion termino con errores.
if "%exitCode%"=="0" echo La publicacion termino correctamente.
pause
exit /b %exitCode%

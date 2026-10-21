@echo off
REM Doble clic para instalar el monitor de Metro de Santiago
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar_windows.ps1" %*
echo.
pause

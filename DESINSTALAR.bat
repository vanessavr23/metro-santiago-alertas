@echo off
REM Doble clic para detener el monitor (elimina la tarea programada; conserva .env y archivos)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar_windows.ps1" -Desinstalar
echo.
pause

@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set LOG_RUN_STAMP=%%i
set LOG_RUN_DIR=logs\%LOG_RUN_STAMP%
if not exist "%LOG_RUN_DIR%" mkdir "%LOG_RUN_DIR%"
rem --- Sincronizar el reloj para minimizar el desfase con el servidor de SUCAMEC ---
rem (puede requerir permisos; si falla, el bucle de reintento del refresco lo cubre igual)
w32tm /resync >nul 2>&1
set ADAPTIVE_HOUR_SELECTION=1
set ADAPTIVE_HOUR_NOON_FULL_BLOCK=1
set GENERAR_CITA_CONFIRM_WINDOW_S=3.5
set GENERAR_CITA_CONFIRM_GRACE_S=2.5
rem --- Multiworker: 8 workers en paralelo ---
set SCHEDULED_MULTIWORKER=1
set SCHEDULED_WORKERS=8
set SCHEDULED_WORKERS_MAX=8
set SCHEDULED_WORKER_MODE=sticky
rem --- Pre-calentamiento: login+navegacion antes de medianoche, golpe a cupos a las 00:00 ---
rem Programar este .bat en el Task Scheduler a las 23:59:00.
rem REGLA ANTI-COLISION: la noche que uses este .bat, DESACTIVA el trigger de run_scheduled.bat (00:00).
rem Ambos leen el mismo Excel y credenciales JV; no deben correr a la vez.
set PREWARM_ENABLE=1
set DISPARO_HHMM=00:00
set PREWARM_KEEPALIVE_MS=40000
set PREWARM_ADELANTO_MS=2500
echo [INFO] Ejecutando pipeline en modo scheduled (PRE-CALENTAMIENTO)...
echo [INFO] Salida detallada: %LOG_RUN_DIR%\task_scheduler_stdout.log

if not exist ".venv\Scripts\python.exe" (
	echo [ERROR] No existe .venv\Scripts\python.exe. Ejecuta: python -m venv .venv ^&^& .venv\Scripts\python.exe -m pip install -r requirements.txt
	endlocal & exit /b 1
)

".venv\Scripts\python.exe" run_pipeline.py --mode scheduled >> "%LOG_RUN_DIR%\task_scheduler_stdout.log" 2>&1
set EXITCODE=%ERRORLEVEL%
if "%EXITCODE%"=="0" (
	echo [OK] Ejecucion finalizada. Revisa %LOG_RUN_DIR%\task_scheduler_stdout.log
) else (
	echo [ERROR] Ejecucion finalizada con codigo %EXITCODE%. Revisa %LOG_RUN_DIR%\task_scheduler_stdout.log
)
endlocal & exit /b %EXITCODE%

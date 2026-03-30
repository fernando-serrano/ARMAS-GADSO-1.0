@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
set ADAPTIVE_HOUR_SELECTION=1
set ADAPTIVE_HOUR_NOON_FULL_BLOCK=1
echo [INFO] Ejecutando pipeline en modo scheduled...
echo [INFO] Salida detallada: logs\task_scheduler_stdout.log
python run_pipeline.py --mode scheduled >> logs\task_scheduler_stdout.log 2>&1
set EXITCODE=%ERRORLEVEL%
if "%EXITCODE%"=="0" (
	echo [OK] Ejecucion finalizada. Revisa logs\task_scheduler_stdout.log
) else (
	echo [ERROR] Ejecucion finalizada con codigo %EXITCODE%. Revisa logs\task_scheduler_stdout.log
)
endlocal & exit /b %EXITCODE%

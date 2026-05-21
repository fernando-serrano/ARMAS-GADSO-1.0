@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
set ADAPTIVE_HOUR_SELECTION=1
set ADAPTIVE_HOUR_NOON_FULL_BLOCK=1
rem Linux/Trixie o Python global:
rem python run_pipeline.py --mode manual --hold-browser-open

if not exist ".venv\Scripts\python.exe" (
	echo [ERROR] No existe .venv\Scripts\python.exe. Ejecuta: python -m venv .venv ^&^& .venv\Scripts\python.exe -m pip install -r requirements.txt
	endlocal & exit /b 1
)

".venv\Scripts\python.exe" run_pipeline.py --mode manual --hold-browser-open
endlocal

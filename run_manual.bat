@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
python run_pipeline.py --mode manual --hold-browser-open
endlocal

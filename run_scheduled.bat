@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
set ADAPTIVE_HOUR_SELECTION=1
set ADAPTIVE_HOUR_NOON_FULL_BLOCK=1
python run_pipeline.py --mode scheduled >> logs\task_scheduler_stdout.log 2>&1
set EXITCODE=%ERRORLEVEL%
endlocal & exit /b %EXITCODE%

@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
python run_pipeline.py --mode scheduled >> logs\task_scheduler_stdout.log 2>&1
set EXITCODE=%ERRORLEVEL%
endlocal & exit /b %EXITCODE%

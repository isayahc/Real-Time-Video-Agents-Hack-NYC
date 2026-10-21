@echo off
cd /d "%~dp0"
echo Workbench: http://127.0.0.1:8000/
echo Backend changes reload automatically. Press Ctrl+C to stop.
python -m protocol_pipeline.web --reload
if errorlevel 1 pause

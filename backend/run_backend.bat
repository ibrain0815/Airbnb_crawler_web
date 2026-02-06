@echo off
cd /d "%~dp0"
echo Backend starting at http://127.0.0.1:8000
echo Open browser: http://127.0.0.1:8000/health
echo Press Ctrl+C to stop.
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
pause

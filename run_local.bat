@echo off
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=C:\venv312\Scripts\python.exe"
if not exist "%PY%" set "PY=py -3.12"

echo Killing old processes...
taskkill /F /IM python.exe 2>nul
timeout /t 3 /nobreak >nul

echo Starting backend...
start "Backend" cmd /k "cd /d "%ROOT%" && "%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

timeout /t 5 /nobreak >nul

echo Starting frontend...
start "Frontend" cmd /k "cd /d "%ROOT%" && "%PY%" -m streamlit run frontend/streamlit_app.py --server.port 8501"

echo Both servers starting. Open http://localhost:8501

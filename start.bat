@echo off
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=C:\venv312\Scripts\python.exe"
if not exist "%PY%" set "PY=py -3.12"

echo Killing old processes on ports 8000 and 3000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
timeout /t 2 /nobreak >nul

echo Starting backend...
start "Backend" cmd /k "cd /d "%ROOT%" && "%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

timeout /t 5 /nobreak >nul

echo Starting Next.js frontend...
start "Frontend" cmd /k "cd /d "%ROOT%frontend-next" && npm run dev -- --port 3000"

echo Both servers starting. Open http://localhost:3000

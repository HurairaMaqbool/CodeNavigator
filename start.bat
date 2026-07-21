@echo off
setlocal
set "ROOT=%~dp0"

echo Killing old processes on ports 8000 and 3000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
ping 127.0.0.1 -n 3 >nul

echo Starting backend...
start "Backend" cmd /k "cd /d "%ROOT%" && call .venv\Scripts\activate && uvicorn app.main:app --host 127.0.0.1 --port 8000"

ping 127.0.0.1 -n 6 >nul

echo Starting Next.js frontend...
start "Frontend" cmd /k "cd /d "%ROOT%frontend-next" && npm run dev -- --port 3000"

echo Both servers starting. Open http://localhost:3000

@echo off
rem One-click launcher for Windows. Double-click this file.
cd /d "%~dp0"

where python >nul 2>nul || (echo X Python is not installed. Get it at https://www.python.org/downloads/ & pause & exit /b 1)
where ffmpeg >nul 2>nul || (echo X FFmpeg is not installed. Run: winget install ffmpeg & pause & exit /b 1)

if not exist frontend\dist\index.html (
  where node >nul 2>nul || (echo X Node.js is not installed. Get it at https://nodejs.org & pause & exit /b 1)
  echo Building the web interface (first run only)...
  pushd frontend
  call npm install --no-audit --no-fund --silent
  call npm run build --silent
  popd
)

if not exist backend\.venv (
  echo Creating the Python environment (first run only)...
  python -m venv backend\.venv
)
backend\.venv\Scripts\python -m pip install -q -r backend\requirements.txt

echo Ready. Opening http://localhost:8000  (close this window to stop)
start "" http://localhost:8000
cd backend
..\backend\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

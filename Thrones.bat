@echo off
rem Thrones launcher: starts the local server and opens the app in your browser.
rem Close this window (or press Ctrl+C) to stop Thrones and free the GPU.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Thrones is not set up yet. Run setup first:
  echo     powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
  pause
  exit /b 1
)
if not exist "frontend\dist\index.html" (
  echo The interface has not been built. Run scripts\setup.ps1 first.
  pause
  exit /b 1
)

title Thrones
set PYTHONIOENCODING=utf-8
cd backend
"..\.venv\Scripts\python.exe" -X utf8 -m thrones

@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_dev.ps1"
if errorlevel 1 (
  echo.
  echo Network Launcher did not start.
  echo Install dependencies first:
  echo   python -m pip install -r requirements.txt
  echo.
  pause
)

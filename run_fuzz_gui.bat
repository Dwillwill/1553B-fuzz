@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=python
python --version >nul 2>nul
if errorlevel 1 (
  echo Python was not found in PATH.
  echo Install Python 3.10+ or add python.exe to PATH, then run this script again.
  pause
  exit /b 1
)
python -m mil1553_fuzz.gui
endlocal

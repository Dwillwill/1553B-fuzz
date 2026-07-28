@echo off
setlocal
cd /d "%~dp0"

fltmc >nul 2>nul
if errorlevel 1 (
  echo Administrator rights are required to copy the crash dump.
  echo Right-click this file and select "Run as administrator".
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass ^
  -File "%~dp0tools\collect_bsod_diagnostics.ps1"

if errorlevel 1 (
  echo.
  echo Diagnostic collection failed. Review the message above.
) else (
  echo.
  echo Diagnostic collection completed.
)
pause
endlocal

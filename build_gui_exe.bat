@echo off
setlocal
cd /d "%~dp0"

python --version >nul 2>nul
if errorlevel 1 (
  echo Python was not found in PATH.
  exit /b 1
)

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name 1553B_Fuzz_GUI ^
  --paths python ^
  --distpath dist ^
  --workpath build\pyinstaller ^
  --specpath build ^
  python\fuzz_gui_main.py

if errorlevel 1 exit /b 1

if not exist dist\board_adapter mkdir dist\board_adapter

if not exist board_adapter\mil1553_board_adapter.dll (
  echo Missing board_adapter\mil1553_board_adapter.dll
  echo Run board_adapter\build_windows_x64.bat first.
  exit /b 1
)

if not exist board_adapter\mil1553api.dll (
  echo Missing board_adapter\mil1553api.dll
  echo Copy the vendor mil1553api.dll into board_adapter first.
  exit /b 1
)

copy /Y board_adapter\mil1553_board_adapter.dll dist\board_adapter\mil1553_board_adapter.dll >nul
copy /Y board_adapter\mil1553api.dll dist\board_adapter\mil1553api.dll >nul

echo.
echo Portable build completed:
echo   dist\1553B_Fuzz_GUI.exe
echo   dist\board_adapter\mil1553_board_adapter.dll
echo   dist\board_adapter\mil1553api.dll
endlocal

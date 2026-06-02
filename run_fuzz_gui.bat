@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=python
python -m mil1553_fuzz.gui
endlocal

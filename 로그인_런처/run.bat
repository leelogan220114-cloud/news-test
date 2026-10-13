@echo off
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -m pip install -q selenium openpyxl
%PY% login_launcher.py
if errorlevel 1 echo.
if errorlevel 1 echo [ERROR] Python is not installed or failed to run. Please install Python from python.org ^(check "Add Python to PATH"^).
pause

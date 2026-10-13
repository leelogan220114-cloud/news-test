@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (set PY=python& set PYW=pythonw) else (set PY=py& set PYW=pyw)
%PY% -c "import selenium, openpyxl" >nul 2>nul || %PY% -m pip install -q selenium openpyxl
%PY% -c "import tkinter, selenium, openpyxl" >nul 2>nul
if errorlevel 1 goto fail
start "" %PYW% login_launcher.py
exit /b 0
:fail
echo [ERROR] Python or required packages are missing.
echo Install Python from python.org and check "Add Python to PATH", then run again.
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install -q selenium openpyxl
python 로그인_런처.py
pause

@echo off
rem Double-click this file to see how many JSearch requests you have left.
cd /d "%~dp0"
.venv\Scripts\python.exe usage.py
echo.
pause

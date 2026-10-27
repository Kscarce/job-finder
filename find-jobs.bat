@echo off
rem Double-click this file to search for new jobs, then score and rank them.
rem It works from anywhere, because it switches to this folder first.
cd /d "%~dp0"
.venv\Scripts\python.exe fetch_jobs.py
.venv\Scripts\python.exe score_jobs.py
echo.
pause

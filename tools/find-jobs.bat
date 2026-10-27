@echo off
rem Double-click this file to search for new jobs, then score and rank them,
rem without opening the app. Works from anywhere: it switches to the project folder first.
cd /d "%~dp0.."
.venv\Scripts\python.exe jobfinder\fetch_jobs.py
.venv\Scripts\python.exe jobfinder\score_jobs.py
echo.
pause

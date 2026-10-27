@echo off
rem Double-click this file to re-score and rank the jobs you already have.
rem Uses no JSearch requests. Good after you change your resume or settings.
cd /d "%~dp0.."
.venv\Scripts\python.exe jobfinder\score_jobs.py
echo.
pause

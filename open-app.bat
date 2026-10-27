@echo off
rem Double-click this file to open the Job Finder app in your web browser.
rem Keep this black window open while you use the app; close it to stop the app.
cd /d "%~dp0"
echo Starting Job Finder... your browser will open in a few seconds.
echo Keep this window open while you use the app. Close it when you're done.
echo.
rem Open the browser after a short wait, so the app has time to start.
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8501"
.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501

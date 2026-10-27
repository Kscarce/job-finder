@echo off
rem Double-click this file once to install Job Finder on Windows.
rem It sets up a private copy of Python's packages in this folder (.venv).
cd /d "%~dp0"
echo Installing Job Finder. This takes about 5-10 minutes the first time.
echo.

rem --- Find Python 3.11, 3.12 or 3.13 (PyTorch doesn't support newer versions yet) ---
set PY=
for %%V in (3.13 3.12 3.11) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set PY=py -%%V
    )
)
if not defined PY (
    echo Python 3.13 wasn't found. Trying to install it with Windows' Python installer...
    py install 3.13 >nul 2>&1 && set PY=py -3.13
)
if not defined PY (
    echo.
    echo Couldn't find Python 3.11-3.13.
    echo Please install Python 3.13 from https://www.python.org/downloads/
    echo ^(tick "Add python.exe to PATH" during setup^), then run install.bat again.
    pause
    exit /b 1
)
echo Using %PY%

rem --- Create the private environment and install the packages ---
if not exist .venv (
    %PY% -m venv .venv || goto :failed
)
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto :failed

rem --- Check the AI library loads (it needs Microsoft's Visual C++ runtime) ---
.venv\Scripts\python.exe -c "import torch" >nul 2>&1
if errorlevel 1 (
    echo.
    echo One more step: the AI model needs Microsoft's free Visual C++ runtime.
    echo Download and install it from: https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo Then double-click open-app.bat.
    pause
    exit /b 0
)

echo.
echo Done! Double-click open-app.bat to start Job Finder.
pause
exit /b 0

:failed
echo.
echo Something went wrong during install. Check your internet connection and try again.
pause
exit /b 1

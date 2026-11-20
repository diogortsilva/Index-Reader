@echo off
rem Index-Reader launcher for Windows: double-click to open the window.
rem The first launch creates a private Python environment in the .venv folder
rem and downloads openpyxl, the one library the tool needs. After that it runs offline.
setlocal
cd /d "%~dp0"
title Index-Reader

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY goto nopython

if exist ".venv\Scripts\python.exe" goto havevenv
echo First launch: setting up Index-Reader (needs the internet once)...
%PY% -m venv .venv
if errorlevel 1 goto systempython

:havevenv
".venv\Scripts\python.exe" -c "import openpyxl" >nul 2>nul
if not errorlevel 1 goto launchvenv
echo Installing openpyxl...
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto noinstall

:launchvenv
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m index_reader
) else (
    ".venv\Scripts\python.exe" -m index_reader
)
goto end

:systempython
rem No environment could be created: fall back to the Python that is installed.
%PY% -c "import openpyxl" >nul 2>nul
if errorlevel 1 goto noinstall
%PY% -m index_reader
if errorlevel 1 pause
goto end

:nopython
echo Python 3 was not found on this computer.
echo Install Python 3.9 or newer, or use the packaged Index-Reader.exe instead.
pause
goto end

:noinstall
echo.
echo The openpyxl library is not available and could not be installed.
echo On a computer without internet access, use the packaged Index-Reader.exe instead.
pause

:end
endlocal

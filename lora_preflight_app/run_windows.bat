@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"

if "%PYTHON_CMD%"=="" (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=python"
)

rem A .venv copied from another PC breaks when its base Python
rem (e.g. Anaconda) does not exist here. Verify it and rebuild if broken.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
  if errorlevel 1 (
    echo Existing .venv is broken - rebuilding it...
    rmdir /s /q ".venv"
  )
)

if exist ".venv\Scripts\python.exe" goto :install

if "%PYTHON_CMD%"=="" (
  echo Python was not found on this PC.
  echo Install Python 3.11 from https://www.python.org/downloads/
  echo and then run this file again.
  pause
  exit /b 1
)

echo Creating local Python environment...
%PYTHON_CMD% -m venv .venv
if errorlevel 1 (
  echo Failed to create .venv.
  pause
  exit /b 1
)

:install
if exist "wheelhouse" (
  echo Installing bundled packages without internet...
  ".venv\Scripts\python.exe" -m pip install --no-index --find-links "%~dp0wheelhouse" -r requirements.txt
  if errorlevel 1 (
    echo Bundled install failed - trying online install...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  )
) else (
  echo Installing packages from requirements.txt...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

if errorlevel 1 (
  echo Package install failed.
  echo If this keeps happening: install Python 3.11 from python.org,
  echo delete the .venv folder, and run this file again.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" app.py
exit /b %ERRORLEVEL%

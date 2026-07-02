@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>nul
if %ERRORLEVEL%==0 set "PYTHON_CMD=py -3"

if "%PYTHON_CMD%"=="" (
  where python >nul 2>nul
  if %ERRORLEVEL%==0 set "PYTHON_CMD=python"
)

if "%PYTHON_CMD%"=="" (
  echo Python was not found.
  echo Install Python 3.10 or later, then run this file again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating local Python environment...
  %PYTHON_CMD% -m venv .venv
  if %ERRORLEVEL% neq 0 (
    echo Failed to create .venv.
    pause
    exit /b %ERRORLEVEL%
  )
)

if exist "wheelhouse" (
  echo Installing bundled packages without internet...
  ".venv\Scripts\python.exe" -m pip install --no-index --find-links "%~dp0wheelhouse" -r requirements.txt
) else (
  echo Installing packages from requirements.txt...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

if %ERRORLEVEL% neq 0 (
  echo Package install failed.
  pause
  exit /b %ERRORLEVEL%
)

".venv\Scripts\python.exe" app.py
exit /b %ERRORLEVEL%

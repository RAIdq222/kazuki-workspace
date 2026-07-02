@echo off
chcp 65001 >nul
rem ===== ep7 genzu handoff: gather -> commit -> push (one click) =====
rem Run from repo root (kazuki-workspace).
rem GENZU defaults to ..\00.原図 (one level above the repo). Edit if different.
rem Target cuts are the default set in scripts\gather_handoff_ep7.py.

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "GENZU=..\00.原図"
set "CONTE="

if not exist "%GENZU%" (
  echo [!] genzu folder not found: %GENZU%
  echo     Edit GENZU in run_gather.bat to the real full path.
  pause & exit /b 1
)

echo === Exporting genzu to handoff/ep7 (large PSDs may take minutes) ===
if "%CONTE%"=="" (
  python "%~dp0scripts\gather_handoff_ep7.py" --genzu-dir "%GENZU%"
) else (
  python "%~dp0scripts\gather_handoff_ep7.py" --genzu-dir "%GENZU%" --conte-dir "%CONTE%"
)

rem --- git identity must be set by the operator (do not impersonate) ---
set "GEMAIL="
for /f "tokens=*" %%i in ('git config user.email 2^>nul') do set "GEMAIL=%%i"
if not defined GEMAIL (
  echo [!] git identity is not set. Set it once, then re-run:
  echo     git config --global user.email "you@example.com"
  echo     git config --global user.name  "Your Name"
  pause & exit /b 1
)

rem --- size warning: handoff/ep7 is committed to a SHARED repo (bloats clone/pull) ---
echo === Review before pushing (handoff/ep7 goes into the shared git repo) ===
dir /s /-c "handoff\ep7" | find "bytes"
choice /c YN /m "Commit and push handoff/ep7 now"
if errorlevel 2 (
  echo Skipped push. Inspect handoff/ep7 and commit manually if needed.
  pause & exit /b 0
)

echo === git add / commit / push ===
git add handoff/ep7
git commit -m "data: ep7 genzu handoff"
git push

echo.
echo Done. Other sessions: git pull, then read handoff/ep7/cutNNN/genzu_visible.png
pause

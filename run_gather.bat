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

rem --- ensure a git identity exists (commit fails otherwise) ---
set "GEMAIL="
for /f "tokens=*" %%i in ('git config user.email 2^>nul') do set "GEMAIL=%%i"
if not defined GEMAIL (
  echo Setting a local git identity (was unset)...
  git config user.email "kuroe@creatorsx.jp"
  git config user.name "kuroe"
)

echo === git add / commit / push ===
git add handoff/ep7
git commit -m "data: ep7 genzu handoff (10 cuts)"
git push

echo.
echo Done. Other sessions: git pull, then read handoff/ep7/cutNNN/genzu_visible.png
pause

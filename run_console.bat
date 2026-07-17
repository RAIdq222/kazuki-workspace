@echo off
chcp 65001 >nul
rem ===== genzu console launcher (all works via runs/project_*.json) =====
rem Run from repo root. All registered works (runs/project_*.json) load as tabs.
rem To add a work: create runs/project_<work>_<ep>.json (see docs/asset-discovery.md)
rem or use the "+work" button in the console UI.

setlocal
cd /d "%~dp0"

set "PORT=8765"

echo Starting console... open http://127.0.0.1:%PORT% in your browser.
python "%~dp0run_console.py" --port %PORT%
pause

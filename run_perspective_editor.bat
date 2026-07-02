@echo off
rem ==== Perspective editor one-click launch (Windows) ====
rem Put this batch at the repo root (kazuki-workspace) and run it.
rem Open http://127.0.0.1:PORT in your browser, then enter an image path.

setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "PORT=8770"

echo Starting... open http://127.0.0.1:%PORT% in your browser.
python "%~dp0run_perspective_editor.py" --port %PORT% %*
pause

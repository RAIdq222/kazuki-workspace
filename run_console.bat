@echo off
rem ==== 原図修正コンソール ワンクリック起動 (Windows) ====
rem このバッチはリポジトリ直下(kazuki-workspace)に置いて実行する。
rem 原図/出力フォルダがリポジトリの一つ上(尚善_原図修正自動化検証\..)にある前提で
rem 相対パスを既定にしてある。違う場所なら下の3行を書き換えてください。

setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "GENZU=..\00.原図"
set "OUT=..\10.生成結果"
set "BOARDS="
set "PORT=8765"

if not exist "%GENZU%" (
  echo [!] 原図フォルダが見つかりません: %GENZU%
  echo     run_console.bat 内の GENZU を実際のフルパスに書き換えてください。
  pause & exit /b 1
)

echo 起動中... ブラウザで http://127.0.0.1:%PORT% を開いてください。
if "%BOARDS%"=="" (
  python "%~dp0run_console.py" --genzu-dir "%GENZU%" --out "%OUT%" --port %PORT%
) else (
  python "%~dp0run_console.py" --genzu-dir "%GENZU%" --out "%OUT%" --boards-dir "%BOARDS%" --port %PORT%
)
pause

@echo off
rem ==== ep7 原図の受け渡し: gather → commit → push をワンクリック (Windows) ====
rem リポジトリ直下(kazuki-workspace)に置いて実行する。
rem 原図フォルダがリポジトリの一つ上(..\00.原図)にある前提。違う場合は GENZU を書き換える。
rem 対象カットは scripts\gather_handoff_ep7.py の既定(15,23,47,53,207,240,257,274,293,294)。

setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "GENZU=..\00.原図"
set "CONTE="

if not exist "%GENZU%" (
  echo [!] 原図フォルダが見つかりません: %GENZU%
  echo     run_gather.bat の GENZU を実際のフルパスに書き換えてください。
  pause & exit /b 1
)

echo === 原図を handoff/ep7 へ書き出し中（大きいPSDは数分かかることがあります）===
if "%CONTE%"=="" (
  python "%~dp0scripts\gather_handoff_ep7.py" --genzu-dir "%GENZU%"
) else (
  python "%~dp0scripts\gather_handoff_ep7.py" --genzu-dir "%GENZU%" --conte-dir "%CONTE%"
)

echo.
echo === git で受け渡し（commit / push）===
git add handoff/ep7
git commit -m "data: ep7 10カットの原図受け渡し"
git push

echo.
echo 完了。別セッションで git pull すれば handoff/ep7/cut<NN>/genzu*.png を読めます。
pause

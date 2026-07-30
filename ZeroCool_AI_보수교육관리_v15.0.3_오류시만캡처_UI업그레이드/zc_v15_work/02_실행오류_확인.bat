@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ZeroCool AI Startup Diagnostics
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "APP=%~dp0app\launcher_v3.py"
set "SHARED_PY=%LOCALAPPDATA%\ZeroCoolAI\EducationManager\venv\Scripts\python.exe"
set "LOCAL_PY=%~dp0.venv\Scripts\python.exe"

if exist "%LOCAL_PY%" (
  "%LOCAL_PY%" "%APP%"
  goto END
)
if exist "%SHARED_PY%" (
  "%SHARED_PY%" "%APP%"
  goto END
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%APP%"
  goto END
)
python "%APP%"

:END
echo.
echo 프로그램이 종료되었습니다. 위에 오류가 표시되면 화면을 캡처해 주세요.
pause

@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ZeroCool AI Education Manager
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "APP=%~dp0app\launcher_v3.py"
set "REQ=%~dp0app\requirements.txt"
set "SHARED_ROOT=%LOCALAPPDATA%\ZeroCoolAI\EducationManager"
set "SHARED_VENV=%SHARED_ROOT%\venv"
set "SHARED_PY=%SHARED_VENV%\Scripts\python.exe"
set "SHARED_PYW=%SHARED_VENV%\Scripts\pythonw.exe"
set "LOCAL_PY=%~dp0.venv\Scripts\python.exe"
set "LOCAL_PYW=%~dp0.venv\Scripts\pythonw.exe"

if not exist "%APP%" goto APP_MISSING

rem 1) Reuse an environment already installed in this folder.
if exist "%LOCAL_PY%" (
  "%LOCAL_PY%" -c "import pandas,openpyxl,xlrd,selenium,win32com" >nul 2>nul
  if not errorlevel 1 goto RUN_LOCAL
)

rem 2) Reuse the shared environment across all program versions.
if exist "%SHARED_PY%" (
  "%SHARED_PY%" -c "import pandas,openpyxl,xlrd,selenium,win32com" >nul 2>nul
  if not errorlevel 1 goto RUN_SHARED
)

rem 3) Reuse packages already installed in Windows Python.
set "SYS_KIND="
where py >nul 2>nul && set "SYS_KIND=PY"
if not defined SYS_KIND where python >nul 2>nul && set "SYS_KIND=PYTHON"
if not defined SYS_KIND goto PYTHON_MISSING

if "%SYS_KIND%"=="PY" (
  py -3 -c "import pandas,openpyxl,xlrd,selenium,win32com" >nul 2>nul
  if not errorlevel 1 goto RUN_SYSTEM_PY
) else (
  python -c "import pandas,openpyxl,xlrd,selenium,win32com" >nul 2>nul
  if not errorlevel 1 goto RUN_SYSTEM_PYTHON
)

rem 4) Only when dependencies are missing, install them once in a shared folder.
echo.
echo [ZeroCool AI] Required components are not ready.
echo The program will prepare them automatically one time only.
echo Future versions will reuse the same installation.
echo.
if not exist "%SHARED_ROOT%" mkdir "%SHARED_ROOT%" >nul 2>nul
if "%SYS_KIND%"=="PY" (
  py -3 -m venv "%SHARED_VENV%"
) else (
  python -m venv "%SHARED_VENV%"
)
if errorlevel 1 goto SETUP_FAILED
"%SHARED_PY%" -m pip install --disable-pip-version-check --upgrade pip
if errorlevel 1 goto SETUP_FAILED
"%SHARED_PY%" -m pip install --disable-pip-version-check -r "%REQ%"
if errorlevel 1 goto SETUP_FAILED
goto RUN_SHARED

:RUN_LOCAL
start "" "%LOCAL_PYW%" "%APP%"
exit /b 0

:RUN_SHARED
start "" "%SHARED_PYW%" "%APP%"
exit /b 0

:RUN_SYSTEM_PY
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 "%APP%"
) else (
  start "" py -3 "%APP%"
)
exit /b 0

:RUN_SYSTEM_PYTHON
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw "%APP%"
) else (
  start "" python "%APP%"
)
exit /b 0

:PYTHON_MISSING
echo.
echo Python 3 was not found on this PC.
echo Install Python 3 once, then run this file again.
echo During installation, enable Add Python to PATH.
echo.
pause
exit /b 1

:SETUP_FAILED
echo.
echo Automatic preparation failed.
echo Check the internet connection, then run 99_Repair_Installation.bat.
echo.
pause
exit /b 1

:APP_MISSING
echo.
echo Program files are missing. Extract the ZIP again.
echo.
pause
exit /b 1

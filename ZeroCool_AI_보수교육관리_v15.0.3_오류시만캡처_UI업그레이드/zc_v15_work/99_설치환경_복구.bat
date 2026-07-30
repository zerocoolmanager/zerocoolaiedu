@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ZeroCool AI Repair
set "ROOT=%LOCALAPPDATA%\ZeroCoolAI\EducationManager"
echo.
echo This will rebuild only the shared program environment.
echo Your Excel files and result files will not be deleted.
echo.
choice /C YN /M "Continue"
if errorlevel 2 exit /b 0
if exist "%ROOT%\venv" rmdir /s /q "%ROOT%\venv"
call "%~dp001_ZeroCool_AI_실행.bat"

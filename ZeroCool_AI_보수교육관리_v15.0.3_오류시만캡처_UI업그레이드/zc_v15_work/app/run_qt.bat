@echo off
cd /d "%~dp0"
python qt_launcher.py
if errorlevel 1 pause

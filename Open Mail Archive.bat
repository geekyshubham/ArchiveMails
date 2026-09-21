@echo off
cd /d "%~dp0"
py -3 serve.py --open
if errorlevel 1 pause

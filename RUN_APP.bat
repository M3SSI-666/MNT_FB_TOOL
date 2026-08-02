@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: ============================================================
::  MNT FB AutoPost - mo CUA SO APP (pywebview, khong hien CMD)
::  Nhan X de dong app se tat sach: server + runner dang nen.
:: ============================================================

call "%~dp0_TIM_PYTHON.bat"
if errorlevel 1 exit /b 1

start "" %PYW% -X utf8 server.py

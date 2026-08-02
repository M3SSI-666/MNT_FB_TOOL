@echo off
cd /d "%~dp0"

:: ============================================================
::  MNT FB AutoPost — chay NEN (khong cua so, khong CMD)
::  Server lang nghe 127.0.0.1:8080 - mo trinh duyet vao localhost:8080.
::  Dung lai: bam "Tat phan mem" trong bang dieu khien.
:: ============================================================

call "%~dp0_TIM_PYTHON.bat"
if errorlevel 1 exit /b 1

start "" %PYW% -X utf8 server.py --no-browser

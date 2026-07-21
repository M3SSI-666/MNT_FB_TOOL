@echo off
echo ============================================================
echo  Dang tat toan bo server + scheduler cu...
echo ============================================================

:: Kill Flask server (port 8080) — KHONG dung /T de tranh diet chrome.exe con
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING 2^>nul') do (
    echo  Kill Flask server PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

:: Kill tat ca orphan scheduler.py (ca python.exe lan pythonw.exe)
echo  Kill orphan scheduler.py...
wmic process where "(name='python.exe' or name='pythonw.exe') and CommandLine like '%%scheduler.py%%'" delete >nul 2>&1

:: Kill join_groups_worker.py
wmic process where "(name='python.exe' or name='pythonw.exe') and CommandLine like '%%join_groups_worker%%'" delete >nul 2>&1

ping -n 3 127.0.0.1 >nul

echo  Khoi dong lai MNT FB AutoPost (cua so app)...
cd /d "%~dp0"
:: Mo lai cua so app (pywebview). Server cu da bi kill o tren nen cua so cu
:: da dong; lenh nay mo cua so moi voi code moi.
start "" pythonw -X utf8 server.py
exit

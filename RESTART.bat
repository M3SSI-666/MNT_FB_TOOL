@echo off
echo ============================================================
echo  Dang tat toan bo server + scheduler cu...
echo ============================================================

:: Kill Flask server (port 8080) — KHONG dung /T de tranh diet chrome.exe con
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING 2^>nul') do (
    echo  Kill Flask server PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

:: Kill orphan scheduler.py + join_groups_worker.py (ca python.exe lan pythonw.exe)
:: Dung PowerShell/CIM thay cho wmic — Microsoft dang go dan wmic khoi Windows 11,
:: mat no thi khong diet duoc runner cu -> 2 runner cung chay tren 1 profile Chrome.
echo  Kill orphan scheduler / join worker...
:: Luu y cu phap: chi dung NHAY DON ben trong. Trong batch, dau | nam trong
:: ngoac kep khong can ^ (viet ^| thi PowerShell nhan dung ky tu ^| va bao loi),
:: va \" cung khong phai escape hop le cua cmd.
powershell -NoProfile -NonInteractive -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and ($_.CommandLine -like '*scheduler.py*' -or $_.CommandLine -like '*join_groups_worker*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

ping -n 3 127.0.0.1 >nul

echo  Khoi dong lai MNT FB AutoPost (cua so app)...
cd /d "%~dp0"
:: Mo lai cua so app (pywebview). Server cu da bi kill o tren nen cua so cu
:: da dong; lenh nay mo cua so moi voi code moi.
call "%~dp0_TIM_PYTHON.bat"
if errorlevel 1 exit /b 1
start "" %PYW% -X utf8 server.py
exit

@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

:: ============================================================
::  MNT FB AutoPost - CAP NHAT phien ban moi nhat
:: ------------------------------------------------------------
::  Client chi can BAM DUP file nay. No se:
::    1. Kiem tra / cai git neu chua co
::    2. Tat app dang chay (server + runner nen)
::    3. Tai code moi nhat tu GitHub (git pull)
::       -> KHONG dung vao data\ cookies\ profiles\ (da .gitignore)
::    4. Cai them thu vien neu requirements.txt doi
::    5. Mo lai app -> db.py tu nang cap schema
::  DU LIEU (tai khoan, cookie, lich, profile) GIU NGUYEN.
:: ============================================================

echo ============================================================
echo  MNT FB AutoPost - Cap nhat phien ban moi nhat
echo ============================================================
echo.

:: --- [0] Phai la thu muc git (da SETUP bang git clone) ---
if not exist ".git" (
    echo [LOI] Thu muc nay chua duoc cai bang git.
    echo       Ban dang chay tu ban giai nen ZIP cu.
    echo.
    echo   Cach xu ly: chay SETUP.bat mot lan de cai lai bang git,
    echo   HOAC lien he nguoi cung cap phan mem de duoc huong dan.
    echo.
    pause
    exit /b 1
)

:: --- [1] Kiem tra git, tu cai neu thieu ---
:: Toan bo viec tim va cai git nam trong _TIM_GIT.bat (xem giai thich trong do).
:: Ban cu chi thu moi "git --version" roi doi hoi winget, thieu winget la bo
:: cuoc — nen may khong co winget khong bao gio update duoc.
echo [1/5] Kiem tra git...
call "%~dp0_TIM_GIT.bat"
if errorlevel 1 (
    pause
    exit /b 1
)
:: Tu kiem lai chu khong tin moi ma tra ve: neu vi ly do nao do git van chua
:: goi duoc thi bao ngay o day, con hon de buoc [3] chet giua chung sau khi
:: app da bi tat.
git --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Van chua dung duoc lenh git.
    echo       Dong cua so nay roi bam lai UPDATE.bat.
    pause
    exit /b 1
)
echo [OK] git san sang.
echo.

:: --- [2] Tat app dang chay (giong RESTART.bat) ---
echo [2/5] Dang tat app dang chay...
:: Kill Flask server (:8080) - KHONG dung /T de tranh diet chrome.exe con
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
:: Kill orphan scheduler.py + join_groups_worker.py (python.exe / pythonw.exe)
powershell -NoProfile -NonInteractive -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and ($_.CommandLine -like '*scheduler.py*' -or $_.CommandLine -like '*join_groups_worker*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
ping -n 3 127.0.0.1 >nul
echo.

:: --- [3] Tai code moi nhat ---
echo [3/5] Dang tai code moi nhat tu GitHub...
:: Bo qua thay doi cuc bo cua file da theo doi (vd client lo sua) de pull khong ket.
:: data/ cookies/ profiles/ nam trong .gitignore nen git KHONG dong vao -> an toan.
git fetch origin >nul 2>&1
for /f %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set BRANCH=%%b
if "!BRANCH!"=="" set BRANCH=main
git reset --hard "origin/!BRANCH!"
if errorlevel 1 (
    echo [LOI] Tai code that bai. Kiem tra ket noi mang roi thu lai.
    pause
    exit /b 1
)
echo.

:: --- [4] Cai them thu vien neu doi ---
echo [4/5] Kiem tra thu vien Python...
pip install -r requirements.txt --disable-pip-version-check -q
if errorlevel 1 (
    echo [Chu y] Cai thu vien co van de - app van co the chay voi thu vien cu.
)
echo.

:: --- [5] Mo lai app ---
echo [5/5] Dang mo lai app...
call "%~dp0_TIM_PYTHON.bat"
if errorlevel 1 exit /b 1
start "" %PYW% -X utf8 server.py

echo.
echo ============================================================
if exist "version.txt" (
    set /p VER=<version.txt
    echo  XONG! Da cap nhat len phien ban: !VER!
) else (
    echo  XONG! Da cap nhat phien ban moi nhat.
)
echo  Du lieu cua ban duoc giu nguyen.
echo ============================================================
echo.
echo  (Cua so nay tu dong dong sau 5 giay)
ping -n 6 127.0.0.1 >nul
exit

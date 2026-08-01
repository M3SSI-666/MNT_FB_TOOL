@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

:: ============================================================
::  MNT FB AutoPost - CAI DAT LAN DAU (bang git)
:: ------------------------------------------------------------
::  Dung file nay THAY CHO viec giai nen ZIP. No se:
::    1. Cai git neu chua co
::    2. Tai (git clone) toan bo code ve thu muc MNT_FB_TOOL
::    3. Chay INSTALL.bat de cai Python packages + Chromium + Tailscale
::  Sau nay muon cap nhat: chi bam UPDATE.bat.
:: ============================================================

:: >>> NGUOI CUNG CAP PHAN MEM: dien link repo GitHub cua ban vao day <<<
::     (repo PUBLIC nen client khong can dang nhap gi)
set "REPO_URL=https://github.com/M3SSI-666/MNT_FB_TOOL.git"

echo ============================================================
echo  MNT FB AutoPost - Cai dat lan dau
echo ============================================================
echo.

if "%REPO_URL%"=="https://github.com/TAI-KHOAN/MNT_FB_TOOL.git" (
    echo [LOI] File SETUP.bat chua duoc dien link repo.
    echo       Nguoi cung cap phan mem can sua dong "set REPO_URL=..."
    echo       o dau file thanh link repo GitHub that.
    pause
    exit /b 1
)

:: --- [1] Kiem tra / cai git ---
git --version >nul 2>&1
if errorlevel 1 (
    echo [1/3] Chua co git - dang thu cai qua winget...
    where winget >nul 2>&1
    if errorlevel 1 (
        echo [LOI] May khong co winget. Tai git thu cong tai:
        echo       https://git-scm.com/download/win
        echo       Cai xong roi mo lai SETUP.bat.
        pause
        exit /b 1
    )
    winget install --id Git.Git -e --accept-package-agreements --accept-source-agreements --silent
    for /f "usebackq tokens=2,*" %%A in (`reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul`) do set "SYSPATH=%%B"
    set "PATH=%SYSPATH%;%PATH%;C:\Program Files\Git\cmd"
    git --version >nul 2>&1
    if errorlevel 1 (
        echo [Chu y] Da cai git nhung cua so nay chua nhan.
        echo         Dong SETUP.bat roi mo lai la duoc.
        pause
        exit /b 1
    )
    echo [OK] Da cai git.
) else (
    echo [1/3] git da co san.
)
echo.

:: --- [2] Tai code ve (git clone) ---
:: Clone vao thu muc con MNT_FB_TOOL ngay canh file SETUP.bat nay.
cd /d "%~dp0"
if exist "MNT_FB_TOOL\.git" (
    echo [2/3] Da co san thu muc MNT_FB_TOOL - bo qua clone.
    echo       Muon cap nhat, vao trong do bam UPDATE.bat.
) else (
    echo [2/3] Dang tai code ve...
    git clone "%REPO_URL%" MNT_FB_TOOL
    if errorlevel 1 (
        echo [LOI] Tai code that bai. Kiem tra:
        echo       - Ket noi mang
        echo       - Link repo dung va dang o che do PUBLIC
        pause
        exit /b 1
    )
    echo [OK] Da tai xong.
)
echo.

:: --- [3] Chay INSTALL.bat (Python packages + Chromium + Tailscale) ---
echo [3/3] Dang cai dat moi truong (co the mat vai phut)...
cd /d "%~dp0MNT_FB_TOOL"
if exist "INSTALL.bat" (
    call INSTALL.bat
) else (
    echo [LOI] Khong tim thay INSTALL.bat trong code vua tai.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Cai dat hoan tat!
echo  Tu nay:
echo    - Chay app:      MNT_FB_TOOL\RUN_APP.bat
echo    - Cap nhat moi:  MNT_FB_TOOL\UPDATE.bat
echo ============================================================
pause

@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

:: ============================================================
::  MNT FB AutoPost - CAI DAT LAN DAU (bang git)
:: ------------------------------------------------------------
::  Dung file nay THAY CHO viec giai nen ZIP. No se:
::    1. Cai git neu chua co
::    2. Tai (git clone) toan bo code ve thu muc MNT_FB_TOOL
::    3. Chay INSTALL.bat de cai Python packages + Chromium
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

:: TH1: dang dung o BAN DA GIAI NEN san (canh SETUP.bat co luon server.py).
::      Khong can clone gi ca - chay INSTALL.bat ngay tai cho.
if exist "%~dp0server.py" (
    echo [2/3] Da co san ma nguon ngay tai thu muc nay - bo qua tai ve.
    set "DICH=%~dp0"
    goto :caidat
)

:: TH2: da clone tu truoc (co .git) -> giu nguyen, khong dong vao.
if exist "MNT_FB_TOOL\.git" (
    echo [2/3] Da cai tu truoc o thu muc MNT_FB_TOOL - bo qua tai ve.
    echo       Muon cap nhat len ban moi: vao trong do bam UPDATE.bat.
    set "DICH=%~dp0MNT_FB_TOOL"
    goto :caidat
)

:: TH3: thu muc MNT_FB_TOOL da ton tai nhung KHONG phai repo git.
::      git clone se bao "already exists and is not an empty directory".
::      Thuong do lan cai truoc bi ngat giua chung, hoac da giai nen zip vao day.
if exist "MNT_FB_TOOL" (
    dir /a /b "MNT_FB_TOOL" 2>nul | findstr "." >nul
    if not errorlevel 1 (
        if exist "MNT_FB_TOOL\server.py" (
            echo [2/3] Thu muc MNT_FB_TOOL da co san ma nguon - bo qua tai ve.
            set "DICH=%~dp0MNT_FB_TOOL"
            goto :caidat
        )
        echo.
        echo  [DUNG LAI] Da co thu muc "MNT_FB_TOOL" nhung khong phai ban cai hop le
        echo             ^(khong co .git, cung khong co server.py^).
        echo             Co the lan cai truoc bi ngat giua chung.
        echo.
        echo   Cach xu ly: DOI TEN hoac XOA thu muc MNT_FB_TOOL do di,
        echo               roi chay lai SETUP.bat.
        echo.
        pause
        exit /b 1
    )
    rmdir "MNT_FB_TOOL" 2>nul
)

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
set "DICH=%~dp0MNT_FB_TOOL"

:caidat
:: %~dp0 luon ket thuc bang dau \, de nguyen thi cd /d "...\" hong va moi lenh
:: sau do chay sai thu muc. Cat dau \ cuoi truoc khi dung.
if "!DICH:~-1!"=="\" set "DICH=!DICH:~0,-1!"
echo.

:: --- [3] Chay INSTALL.bat (Python packages + Chromium) ---
echo [3/3] Dang cai dat moi truong (co the mat vai phut)...
cd /d "!DICH!"
if exist "!DICH!\INSTALL.bat" (
    call "!DICH!\INSTALL.bat"
) else (
    echo [LOI] Khong tim thay INSTALL.bat trong "!DICH!".
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Cai dat hoan tat!
echo  Tu nay, vao thu muc:
echo    !DICH!
echo  roi:
echo    - Chay app     : RUN_APP.bat
echo    - Cap nhat moi : UPDATE.bat
echo ============================================================
pause

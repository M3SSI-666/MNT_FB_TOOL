@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

:: ============================================================
::  MNT FB AutoPost - DAY CODE LEN GITHUB
:: ------------------------------------------------------------
::  Bam dup file nay la xong: tu add + commit + push.
::  Du lieu ca nhan (data\ cookies\ profiles\ logs\ backup\) nam
::  trong .gitignore nen KHONG BAO GIO bi day len. Truoc khi
::  commit con co buoc kiem tra chan ro ri lam luoi an toan.
:: ============================================================

echo ============================================================
echo  Day code len GitHub
echo ============================================================
echo.

:: --- [0] Phai la thu muc git ---
if not exist ".git" (
    echo [LOI] Thu muc nay chua phai repo git.
    echo       Lien he nguoi cung cap phan mem de duoc huong dan.
    pause
    exit /b 1
)

git --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] May chua cai git. Tai tai: https://git-scm.com/download/win
    pause
    exit /b 1
)

:: --- [1] Xem co gi thay doi khong ---
:: Khong dung find/findstr: neu may co Git Bash thi PATH co the tro sang ban
:: Unix cua cac lenh do va ket qua sai hoan toan. Chi dung cu phap batch thuan.
echo [1/4] Kiem tra thay doi...
set "CHANGES=0"
for /f "delims=" %%A in ('git status --porcelain') do set "CHANGES=1"

if "!CHANGES!"=="0" (
    echo.
    echo  Khong co thay doi nao de day len.
    echo  ^(Code hien tai da giong het tren GitHub^)
    echo.
    pause
    exit /b 0
)

echo.
echo  Cac file da thay doi:
echo  ------------------------------------------------------------
git status --short
echo  ------------------------------------------------------------
echo.

:: --- [2] Nhap mo ta thay doi ---
echo [2/4] Mo ta ngan gon lan sua nay.
echo       ^(De trong roi Enter = tu dien ngay gio^)
echo.
set "MSG="
set /p "MSG=  Mo ta: "

if "!MSG!"=="" (
    for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format \"yyyy-MM-dd HH:mm\""') do set "NOW=%%i"
    set "MSG=Cap nhat code !NOW!"
)
echo.

:: --- [3] Dua file vao + KIEM TRA CHAN RO RI ---
echo [3/4] Chuan bi commit...
git add -A

:: Luoi an toan: neu vi ly do gi ma du lieu ca nhan lot vao thi DUNG NGAY.
:: Repo nay de PUBLIC nen mot lan lo la la lo mat khau/cookie Facebook.
:: So khop bang cu phap thay the chuoi cua batch (!F:abc=!) — khong goi
:: findstr, tranh bi lay nham ban Unix khi may co cai Git Bash.
set LEAK=0
for /f "delims=" %%F in ('git diff --cached --name-only') do (
    set "F=%%F"
    if not "!F:data/app.db=!"=="!F!" set LEAK=1
    if not "!F:backup/=!"=="!F!"     set LEAK=1
    if not "!F:.claude=!"=="!F!"     set LEAK=1
    rem cookies/ va profiles/ chi cho phep dung file .gitkeep
    if not "!F:cookies/=!"=="!F!"  if "!F:.gitkeep=!"=="!F!" set LEAK=1
    if not "!F:profiles/=!"=="!F!" if "!F:.gitkeep=!"=="!F!" set LEAK=1
)
if "!LEAK!"=="1" (
    echo.
    echo  [DUNG LAI] Phat hien du lieu ca nhan trong danh sach sap day len!
    echo             Da huy commit de an toan. Kiem tra lai .gitignore.
    git reset >nul 2>&1
    echo.
    pause
    exit /b 1
)

git commit -q -m "!MSG!"
if errorlevel 1 (
    echo  [LOI] Commit that bai.
    pause
    exit /b 1
)
echo  [OK] Da commit: !MSG!
echo.

:: --- [4] Day len GitHub ---
echo [4/4] Dang day len GitHub...
git push
if errorlevel 1 (
    echo.
    echo  [Chu y] Day len that bai. Thuong do tren GitHub co ban moi hon
    echo          ^(vi du ban da sua tu may khac^). Dang thu tai ve roi day lai...
    echo.
    git pull --rebase
    if errorlevel 1 (
        echo.
        echo  [LOI] Tai ve bi xung dot - can xu ly tay.
        echo        Chup man hinh nay va lien he nguoi ho tro.
        pause
        exit /b 1
    )
    git push
    if errorlevel 1 (
        echo.
        echo  [LOI] Van khong day len duoc. Kiem tra ket noi mang / dang nhap GitHub.
        pause
        exit /b 1
    )
)

echo.
echo ============================================================
echo  XONG! Da day code len GitHub.
echo    %MSG%
echo ============================================================
echo.
echo  (Cua so tu dong dong sau 5 giay)
ping -n 6 127.0.0.1 >nul
exit

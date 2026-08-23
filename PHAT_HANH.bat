@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

:: ============================================================
::  MNT FB AutoPost - PHAT HANH mot phien ban moi
:: ------------------------------------------------------------
::  Lam ba viec, theo dung thu tu:
::    1. Ghi so phien ban moi vao version.txt
::    2. Commit rieng file do
::    3. Gan git tag v<so> va day len GitHub
::
::  Tag la thu cho phep QUAY VE mot ban cu bat ky. Khong co tag thi
::  "khach chon version nao" khong thuc hien duoc, vi khong co moc nao
::  de dung lai.
::
::  Quy uoc so: MAJOR.MINOR.PATCH
::    PATCH  sua loi, khong doi cach dung          1.0.0 -> 1.0.1
::    MINOR  them tinh nang, du lieu cu van chay   1.0.1 -> 1.1.0
::    MAJOR  doi cach dung / du lieu can chuyen    1.1.0 -> 2.0.0
:: ============================================================

echo ============================================================
echo  MNT FB AutoPost - Phat hanh phien ban moi
echo ============================================================
echo.

call "%~dp0_TIM_GIT.bat"
if errorlevel 1 (
    pause
    exit /b 1
)

:: --- Phien ban hien tai ---
set "CU="
if exist "version.txt" set /p CU=<version.txt
if "!CU!"=="" set "CU=(chua co)"
echo   Phien ban hien tai: !CU!
echo.

:: --- Nhan so moi ---
set "MOI=%~1"
if "!MOI!"=="" (
    set /p "MOI=  Nhap so phien ban moi (vd 1.0.1): "
)
if "!MOI!"=="" (
    echo   [HUY] Chua nhap so phien ban.
    pause
    exit /b 1
)

:: --- Chan tag trung: tag da ton tai thi khong the day len ---
git rev-parse "v!MOI!" >nul 2>&1
if not errorlevel 1 (
    echo   [LOI] Tag v!MOI! DA TON TAI. Chon so khac.
    pause
    exit /b 1
)

:: --- Chan phat hanh khi cay lam viec con ban ---
:: Phat hanh ma con thay doi chua commit thi tag tro vao mot trang thai
:: KHONG giong thu dang chay tren may ban - quay ve tag se ra ban khac.
for /f %%i in ('git status --porcelain --untracked-files^=no 2^>nul ^| find /c /v ""') do set BAN=%%i
if not "!BAN!"=="0" (
    echo   [LOI] Con !BAN! thay doi chua commit. Commit het roi hay phat hanh.
    git status --short
    pause
    exit /b 1
)

echo.
echo   Se phat hanh: !CU!  ==^>  !MOI!
set /p "OK=  Dung khong? (y/n): "
if /i not "!OK!"=="y" (
    echo   [HUY]
    exit /b 1
)

:: --- 1. Ghi version.txt (khong xuong dong de .bat doc sach) ---
<nul set /p "=!MOI!" > version.txt

:: --- 2. Commit rieng, NEU co gi de commit ---
:: version.txt co the da mang dung so nay tu truoc (vd lan phat hanh dau tien,
:: so duoc dat trong mot commit khac). Luc do khong co gi de commit, va do la
:: chuyen BINH THUONG - chi con thieu moi tag. Ban dau coi day la loi nen lan
:: phat hanh dau tien luon that bai.
git add version.txt
git diff --cached --quiet
if errorlevel 1 (
    git commit -q -m "Phat hanh v!MOI!"
    if errorlevel 1 (
        echo   [LOI] Commit that bai.
        pause
        exit /b 1
    )
) else (
    echo   version.txt da mang so !MOI! tu truoc - chi gan tag.
)

:: --- 3. Tag + day len ---
git tag -a "v!MOI!" -m "MNT FB AutoPost v!MOI!"
git push -q origin main
git push -q origin "v!MOI!"
if errorlevel 1 (
    echo   [LOI] Day len GitHub that bai. Kiem tra mang roi chay: git push origin main --tags
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   HOAN TAT - da phat hanh v!MOI!
echo ============================================================
echo.
echo   Quay ve ban nay bat ky luc nao:  git checkout v!MOI!
echo   Xem moi ban da phat hanh      :  git tag
echo.
pause

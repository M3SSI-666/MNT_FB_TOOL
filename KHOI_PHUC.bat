@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

:: ============================================================
::  MNT FB AutoPost - KHOI PHUC khi khong cap nhat duoc
:: ------------------------------------------------------------
::  Dung khi bam UPDATE.bat ma no bao loi hoac khong lam gi ca.
::  File nay keo thang ban moi nhat tu GitHub ve, khong qua
::  UPDATE.bat.
::
::  DU LIEU CUA BAN KHONG BI DUNG TOI. Tai khoan, page, content,
::  UID nhom, cookie, profile deu nam trong data\ cookies\
::  profiles\ - cac thu muc do trong .gitignore nen
::  "git reset --hard" khong cham vao.
::
::  CACH DUNG: chep file nay vao thu muc cai dat (cho co
::  RUN_APP.bat) roi bam dup.
::
::  VI SAO CAN FILE NAY: tu 01/08/2026 den 23/08/2026, UPDATE.bat
::  co mot loi cu phap khien no chet ngay dong dau tren MOI may.
::  Khong may nao cap nhat duoc, ma ban sua loi lai nam trong ban
::  cap nhat - nen phai co mot duong vong. File nay tu chua, khong
::  goi bat ky file nao khac trong thu muc, de con chay duoc tren
::  nhung may dang ket o ban rat cu.
:: ============================================================

echo ============================================================
echo  MNT FB AutoPost - Khoi phuc
echo ============================================================
echo.

cd /d "%~dp0"

:: --- [1] Phai dung thu muc cai dat ---
if not exist ".git" (
    echo  [LOI] Day khong phai thu muc cai dat cua phan mem.
    echo.
    echo        Hay chep file nay vao dung thu muc co san RUN_APP.bat
    echo        roi bam dup lai.
    echo.
    echo        Thu muc hien tai: %CD%
    echo.
    pause
    exit /b 1
)

:: --- [2] Phai co git ---
:: Khong goi _TIM_GIT.bat: may dang ket o ban cu co the chua co file do.
:: Tu tim lay, o PATH truoc roi den hai cho cai dat thong thuong.
git --version >nul 2>&1
if errorlevel 1 (
    if exist "%ProgramFiles%\Git\cmd\git.exe" set "PATH=%ProgramFiles%\Git\cmd;!PATH!"
)
git --version >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Git\cmd\git.exe" set "PATH=%LOCALAPPDATA%\Programs\Git\cmd;!PATH!"
)
git --version >nul 2>&1
if errorlevel 1 (
    echo  [LOI] May nay chua cai git.
    echo.
    echo        Tai va cai tai: https://git-scm.com/download/win
    echo        Cai xong dong cua so nay roi bam dup lai file nay.
    echo.
    pause
    exit /b 1
)
echo  [1/4] git san sang.

:: --- [3] Tat app dang chay ---
:: Phai tat truoc khi thay code, khong thi app chay nua cu nua moi.
echo  [2/4] Tat app dang chay...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
powershell -NoProfile -NonInteractive -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and ($_.CommandLine -like '*scheduler.py*' -or $_.CommandLine -like '*join_groups_worker*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
ping -n 3 127.0.0.1 >nul

:: --- [4] Sao luu du lieu ---
:: Lam ca o day chu khong chi trong UPDATE.bat: may dang chay ban rat cu, buoc
:: mo app sau do se chay cac buoc nang cap co san trong code moi, ma vai buoc
:: trong so do XOA cot that va chi chay mot chieu.
echo  [3/4] Sao luu du lieu...
set "SAOLUU=%LOCALAPPDATA%\MNT FB AutoPost\backup"
if not exist "!SAOLUU!" mkdir "!SAOLUU!" >nul 2>&1
for /f "delims=" %%d in ('powershell -NoProfile -NonInteractive -Command "Get-Date -Format yyyyMMdd_HHmmss" 2^>nul') do set "DAU=%%d"
if "!DAU!"=="" set "DAU=khong_ro_gio"
if exist "data\app.db" (
    copy /y "data\app.db" "!SAOLUU!\app_!DAU!.db" >nul 2>&1
    if errorlevel 1 (
        echo  [LOI] Khong sao luu duoc du lieu - DUNG LAI de khong lam mat gi.
        echo        Kiem tra quyen ghi vao: !SAOLUU!
        pause
        exit /b 1
    )
    echo        Da sao luu: !SAOLUU!\app_!DAU!.db
) else (
    echo        ^(chua co du lieu - bo qua^)
)

:: --- [5] Keo ban moi nhat ve ---
echo  [4/4] Tai ban moi nhat tu GitHub...
git fetch --tags --force origin >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [LOI] Khong tai duoc tu GitHub. Kiem tra ket noi mang roi thu lai.
    echo.
    pause
    exit /b 1
)

:: Tag moi nhat theo NGAY TAO. Khong sap theo chu cai: sap chu cai thi v1.10.0
:: dung truoc v1.9.0, tuc la se keo nham ban cu.
set "DICH="
for /f "delims=" %%t in ('git tag --sort^=-creatordate 2^>nul') do (
    if "!DICH!"=="" set "DICH=%%t"
)
if "!DICH!"=="" (
    echo  [LOI] Kho code chua co ban phat hanh nao.
    pause
    exit /b 1
)

git reset --hard "!DICH!"
if errorlevel 1 (
    echo.
    echo  [LOI] Dat code ve ban !DICH! that bai.
    echo        Chup man hinh nay va lien he nguoi ho tro.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  HOAN TAT - da khoi phuc len ban !DICH!
echo ============================================================
echo.
echo  Du lieu cua ban duoc giu nguyen.
echo.
echo  Tu lan sau ban KHONG can file nay nua: mo phan mem, bam vao
echo  so phien ban duoi logo la chon duoc ban de cap nhat.
echo.
echo  Dang mo lai phan mem...
echo.

:: Mo lai app. Sau khi reset thi RUN_APP.bat chac chan da la ban moi.
if exist "RUN_APP.bat" (
    start "" "%~dp0RUN_APP.bat"
) else (
    echo  [Chu y] Khong thay RUN_APP.bat - hay mo phan mem bang tay.
    pause
)
exit /b 0

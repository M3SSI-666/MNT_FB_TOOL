@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

:: ============================================================
::  MNT FB AutoPost - Dong goi MA NGUON de gui may khac
::
::  KHONG kem du lieu nhay cam:
::    - data\        (mat khau, cookie, 2FA, media)
::    - cookies\     (cookie Facebook)
::    - profiles\    (session dang nhap trinh duyet)
::    - logs\ __pycache__\ .pid .png ...
::
::  KHONG kem cong cu QUAN TRI / PHAN PHOI (chi ban goc moi can):
::    - PUSH.bat        day code len GitHub
::    - DONG_GOI.bat    chinh file nay
::    - test_basic.py   test cho nguoi phat trien
::    - .gitignore .gitattributes .git\   cau hinh repo
::
::  Client chi con: RUN_APP / RESTART / INSTALL / UPDATE / SETUP
::                  + AUTOSTART, du de cai va cap nhat.
::  May nhan: cai Python -> chay INSTALL.bat -> RUN_APP.bat
:: ============================================================

echo ============================================================
echo  MNT FB AutoPost - Dong goi ma nguon
echo ============================================================
echo.

:: Ten goi kem ngay gio: MNT_FB_TOOL_YYYYMMDD_HHMM.zip
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set STAMP=%%i
set PKGNAME=MNT_FB_TOOL_%STAMP%
set STAGE=%TEMP%\%PKGNAME%
:: Ghi zip ra thu muc CHA cua du an (ngay ben canh thu muc MNT_FB_TOOL),
:: khong dung %USERPROFILE%\Desktop vi may co the de Desktop trong OneDrive.
for %%I in ("%CD%\..") do set PARENT=%%~fI
set OUTZIP=%PARENT%\%PKGNAME%.zip

:: Don staging cu neu co
if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%"

echo [1/3] Dang chep ma nguon (bo qua du lieu nhay cam)...

:: robocopy /MIR sao chep ca cay thu muc, /XD bo thu muc, /XF bo file.
:: robocopy tra ma thoat 0-7 la BINH THUONG (>=8 moi la loi that su).
robocopy "%CD%" "%STAGE%" /E ^
  /XD data cookies profiles logs backup __pycache__ .git .venv venv .claude .idea .vscode ^
  /XF *.pyc *.pyo *.pid debug_*.png *.png *.zip app.db nul HUONG_DAN_UPDATE.md ^
      PUSH.bat .gitignore .gitattributes test_basic.py "%~nx0" ^
  /NFL /NDL /NJH /NJS /NC /NS >nul
if %ERRORLEVEL% GEQ 8 (
    echo [LOI] Chep file that bai ^(robocopy ma %ERRORLEVEL%^).
    rmdir /s /q "%STAGE%" 2>nul
    pause
    exit /b 1
)

:: Giu lai cac thu muc rong bat buoc de app chay duoc (co .gitkeep)
for %%D in (data cookies profiles logs) do (
    if not exist "%STAGE%\%%D" mkdir "%STAGE%\%%D"
    if not exist "%STAGE%\%%D\.gitkeep" type nul > "%STAGE%\%%D\.gitkeep"
)

:: Don sach thiet bi ao "nul" o goc staging neu robocopy lo tao.
:: Phai dung duong dan UNC \\?\ vi "nul" la ten thiet bi reserved cua Windows,
:: del thuong khong dung toi duoc.
del "\\?\%STAGE%\nul" 2>nul

echo [2/3] Kiem tra an toan ^(khong duoc lot mat khau/cookie^)...

:: Chan tuyet doi. QUET TOAN BO cay thu muc chu KHONG chi vai vi tri co dinh:
:: ban truoc chi soi data\app.db, cookies\*.json, profiles\* nen da de lot
:: backup\app.db.* (ban sao DB day du mat khau/cookie/2FA) vao goi gui di.
:: Bat ky file .db / .db-wal / .db-shm / cookie json nao cung phai chan.
set LEAK=0
set "LEAKFILE="
for /f "delims=" %%F in ('powershell -NoProfile -Command "Get-ChildItem -LiteralPath '%STAGE%' -Recurse -File -Force -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in '.db','.sqlite','.sqlite3' -or $_.Name -like '*.db-*' -or $_.Name -like 'app.db*' -or ($_.Extension -eq '.json' -and $_.DirectoryName -like '*cookies*') } | ForEach-Object { $_.FullName }"') do (
    set LEAK=1
    set "LEAKFILE=%%F"
)
:: Profile trinh duyet: chi cho phep .gitkeep
if exist "%STAGE%\profiles\*" (
    for /f "delims=" %%P in ('dir /a /b "%STAGE%\profiles" 2^>nul') do (
        if /i not "%%P"==".gitkeep" ( set LEAK=1 & set "LEAKFILE=profiles\%%P" )
    )
)

if "!LEAK!"=="1" (
    echo.
    echo  [DUNG LAI] Phat hien du lieu nhay cam trong goi - DA HUY de an toan.
    echo             File dau tien tim thay: !LEAKFILE!
    echo             Them thu muc do vao danh sach /XD trong file nay roi thu lai.
    rmdir /s /q "%STAGE%" 2>nul
    echo.
    pause
    exit /b 1
)

echo [3/3] Dang nen thanh file .zip...
if exist "%OUTZIP%" del /q "%OUTZIP%"
:: Dung .NET ZipFile.CreateFromDirectory thay cho Compress-Archive:
:: Compress-Archive liet ke tung muc trong staging va VAP thiet bi ao "nul"
:: (Windows co ten thiet bi nul o moi thu muc). CreateFromDirectory nen ca
:: cay thu muc theo he thong file that nen khong dinh nul, lai nhanh hon.
powershell -NoProfile -Command ^
  "Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::CreateFromDirectory('%STAGE%', '%OUTZIP%')"
if errorlevel 1 (
    echo [LOI] Nen zip that bai.
    rmdir /s /q "%STAGE%" 2>nul
    pause
    exit /b 1
)

:: Don staging
rmdir /s /q "%STAGE%" 2>nul

echo.
echo ============================================================
echo  XONG! Da tao goi:
echo    %OUTZIP%
echo.
echo  Gui file .zip nay sang may khac, roi o may do:
echo    1. Giai nen ra 1 thu muc.
echo    2. Cai Python 3.11+ ^(tick "Add Python to PATH"^).
echo    3. Chay INSTALL.bat  -^> RUN_APP.bat
echo    4. Nhap lai tai khoan / cookie o bang dieu khien.
echo ============================================================
pause

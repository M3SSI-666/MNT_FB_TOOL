@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

:: ============================================================
::  MNT FB AutoPost - Dong goi MA NGUON de gui may khac
::  Tao file .zip CHI chua code, KHONG kem du lieu nhay cam:
::    - data\        (mat khau, cookie, 2FA, media)
::    - cookies\     (cookie Facebook)
::    - profiles\    (session dang nhap trinh duyet)
::    - logs\ __pycache__\ .pid .png ...
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
  /XD data cookies profiles logs __pycache__ .git .venv venv .claude .idea .vscode ^
  /XF *.pyc *.pyo *.pid debug_*.png *.png *.zip app.db "%~nx0" ^
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

echo [2/3] Kiem tra an toan ^(khong duoc lot mat khau/cookie^)...

:: Chan tuyet doi: neu vi ly do gi con sot DB / cookie / profile thi DUNG lai.
set LEAK=0
if exist "%STAGE%\data\app.db"       set LEAK=1
if exist "%STAGE%\cookies\*.json"    set LEAK=1
if exist "%STAGE%\profiles\*"        (
    dir /a /b "%STAGE%\profiles" 2>nul | findstr /v /x ".gitkeep" >nul && set LEAK=1
)
if "!LEAK!"=="1" (
    echo [LOI] Phat hien du lieu nhay cam trong goi - DA HUY de an toan.
    echo       Kiem tra lai .gitignore va thu lai.
    rmdir /s /q "%STAGE%" 2>nul
    pause
    exit /b 1
)

echo [3/3] Dang nen thanh file .zip...
if exist "%OUTZIP%" del /q "%OUTZIP%"
powershell -NoProfile -Command ^
  "Compress-Archive -Path '%STAGE%\*' -DestinationPath '%OUTZIP%' -Force"
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

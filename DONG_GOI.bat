@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo  MNT FB AutoPost - Dong goi ban TRANG de gui nguoi khac
echo ============================================================
echo.
echo  Ban dong goi se KHONG chua:
echo    - Tai khoan, Page, Content, UID nhom (toan bo data\app.db)
echo    - Lich dang, mat khau truy cap tu xa, secret key
echo    - Cookie, profile trinh duyet, log, anh da upload
echo  Nguoi nhan chay INSTALL.bat roi RUN_APP.bat la co phan mem trang,
echo  tu nhap du lieu cua ho.
echo.

:: Moc thoi gian - dung PowerShell cho khoi phu thuoc dinh dang ngay cua may
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set "STAMP=%%i"

set "PKGNAME=MNT_FB_blank_!STAMP!"
set "STAGE=%TEMP%\MNT_FB_pkg\!PKGNAME!"
set "OUTZIP=%~dp0..\!PKGNAME!.zip"

:: Don staging cu (neu lan truoc bi ngat giua chung)
if exist "%TEMP%\MNT_FB_pkg" rmdir /s /q "%TEMP%\MNT_FB_pkg"
mkdir "!STAGE!"

echo [1/3] Sao chep ma nguon (loai tru du lieu nhay cam)...
robocopy "%~dp0." "!STAGE!" /E ^
  /XD "data" "cookies" "profiles" "__pycache__" ".git" ".venv" "venv" ".claude" ^
  /XF "*.pid" "*.png" "*.pyc" "*.pyo" "*.log" "*.db" "*.db-wal" "*.db-shm" ^
  /NFL /NDL /NJH /NJS /NP >nul
:: robocopy tra ma 0-7 la thanh cong, tu 8 tro len moi la loi that
if errorlevel 8 (
    echo [LOI] Sao chep that bai!
    pause
    exit /b 1
)

:: Tao lai cac thu muc rong (kem placeholder) de phan mem chay duoc ngay
for %%D in (cookies profiles logs) do (
    if not exist "!STAGE!\%%D" mkdir "!STAGE!\%%D"
    if not exist "!STAGE!\%%D\.gitkeep" type nul > "!STAGE!\%%D\.gitkeep"
)

:: Khong gui kem chinh file dong goi nay cho nguoi nhan
if exist "!STAGE!\DONG_GOI.bat" del /q "!STAGE!\DONG_GOI.bat"

echo [2/3] Nen thanh file ZIP...
if exist "!OUTZIP!" del /q "!OUTZIP!"
powershell -NoProfile -Command "Compress-Archive -Path '!STAGE!' -DestinationPath '!OUTZIP!' -Force"
if not exist "!OUTZIP!" (
    echo [LOI] Nen ZIP that bai!
    pause
    exit /b 1
)

echo [3/3] Don dep...
rmdir /s /q "%TEMP%\MNT_FB_pkg"

echo.
echo ============================================================
echo  XONG! File dong goi da tao:
echo.
echo    !PKGNAME!.zip
echo    (nam o thu muc CHA cua thu muc phan mem)
echo.
echo  Gui file .zip nay cho nguoi khac. Ho giai nen roi:
echo    1. Chay INSTALL.bat
echo    2. Chay RUN_APP.bat
echo    3. Tu nhap Tai khoan / Page / Content / UID nhom cua ho.
echo ============================================================
pause
endlocal

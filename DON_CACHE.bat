@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

:: ============================================================
::  MNT FB AutoPost - DON CACHE TRINH DUYET
:: ------------------------------------------------------------
::  Xoa cache Chrome trong profiles\ de giai phong o dia.
::
::  KHONG mat dang nhap: phien dang nhap nam o
::  Default\Network\Cookies, trang thai app nam o Local Storage /
::  IndexedDB - khong thu muc nao bi xoa o day dung toi.
::  Anh huong duy nhat: lan tai trang dau sau khi don cham hon vai giay.
::
::  Binh thuong KHONG can chay file nay: scheduler tu don cache sau
::  moi phien dang/nuoi. Chi dung khi muon don sach ngay lap tuc.
:: ============================================================

echo ============================================================
echo  Don cache trinh duyet
echo ============================================================
echo.

if not exist "profiles" (
    echo [LOI] Khong thay thu muc profiles.
    pause
    exit /b 1
)

:: --- Bat buoc: khong duoc con Chrome/runner nao dang chay ---
echo [1/3] Kiem tra phan mem co dang chay khong...
set BUSY=0
for /f "delims=" %%A in ('powershell -NoProfile -Command "@(Get-Process chrome-headless-shell,chrome,node -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*ms-playwright*' }).Count"') do set BUSY=%%A
for /f "delims=" %%B in ('powershell -NoProfile -Command "@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and ($_.CommandLine -like '*scheduler.py*' -or $_.CommandLine -like '*nuoi_nick*') }).Count"') do set RUN=%%B

if not "!BUSY!"=="0" goto :dangchay
if not "!RUN!"=="0"  goto :dangchay
goto :don

:dangchay
echo.
echo  [DUNG LAI] Dang co runner / trinh duyet cua phan mem chay.
echo             Xoa cache luc nay co the LAM HONG profile.
echo.
echo   Hay dung tat ca runner o tab "Hanh dong" truoc, roi chay lai file nay.
echo.
pause
exit /b 1

:don
echo  [OK] Khong co gi dang chay - an toan de don.
echo.

echo [2/3] Dang tinh dung luong truoc khi don...
for /f "delims=" %%S in ('powershell -NoProfile -Command "'{0:N2}' -f (((Get-ChildItem .\profiles -Recurse -File -Force -ErrorAction SilentlyContinue) | Measure-Object Length -Sum).Sum/1GB)"') do set TRUOC=%%S
echo  Hien tai: !TRUOC! GB
echo.

echo [3/3] Dang xoa cache...
powershell -NoProfile -Command "$d=@('Cache','Code Cache','GPUCache','ShaderCache','GrShaderCache','GraphiteDawnCache','DawnWebGPUCache','DawnGraphiteCache'); foreach($n in $d){ Get-ChildItem .\profiles -Recurse -Directory -Filter $n -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue }; Get-ChildItem .\profiles -Recurse -Directory -Filter 'Service Worker' -ErrorAction SilentlyContinue | ForEach-Object { Get-ChildItem $_.FullName -Directory -Include 'CacheStorage','ScriptCache' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue }"

for /f "delims=" %%S in ('powershell -NoProfile -Command "'{0:N2}' -f (((Get-ChildItem .\profiles -Recurse -File -Force -ErrorAction SilentlyContinue) | Measure-Object Length -Sum).Sum/1GB)"') do set SAU=%%S

echo.
echo ============================================================
echo  XONG!
echo    Truoc : !TRUOC! GB
echo    Sau   : !SAU! GB
echo.
echo  Dang nhap cua cac nick VAN CON NGUYEN.
echo ============================================================
pause

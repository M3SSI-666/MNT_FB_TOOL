@echo off
:: ============================================================
::  Tim git; chua co thi TU CAI. File nay duoc CALL tu UPDATE.bat.
:: ------------------------------------------------------------
::  Tra ve: 0 = da dung duoc lenh git trong cua so nay
::          1 = that bai, da in huong dan cho nguoi dung
::
::  KHONG dat setlocal o day! File nay sua bien PATH cho ca file
::  goi no dung (giong _TIM_PYTHON.bat dat bien PYW). Co setlocal
::  thi PATH vua sua se mat ngay khi thoat, va file goi van bao
::  thieu git y nguyen.
:: ------------------------------------------------------------
::  Vi sao phai lam nhieu buoc the nay: may ve tinh bao "thieu GIT"
::  KHONG chi vi chua cai. Ba nguyen nhan thuong gap va deu KHONG
::  can cai lai gi ca:
::    1. Git da cai nhung cua so cmd nay mo TRUOC luc cai -> PATH cu.
::    2. Git cai kieu per-user, nam o %LOCALAPPDATA%, khong vao PATH may.
::    3. Nguoi dung lo don PATH.
::  Ban cu chi thu moi "git --version" roi doi hoi winget, thieu winget
::  la bo cuoc - nen may khong co winget (Win10 doi cu, chua co App
::  Installer) khong bao gio update duoc.
:: ============================================================

:: --- [0] BAN CAI DAT: git di kem nam ngay trong thu muc, o git\cmd\ ---
:: Uu tien no truoc moi thu khac. Ca diem cua ban cai la khach KHONG phai cai
:: git; di tim git cua he thong roi doi winget cai la quay lai dung cai loi da
:: lam may ve tinh khong cap nhat duoc.
if exist "%~dp0git\cmd\git.exe" (
    set "PATH=%~dp0git\cmd;%PATH%"
    exit /b 0
)

:: --- [1] Dung duoc luon chua? ---
where git >nul 2>&1 && exit /b 0

:: --- [2] Nap lai PATH tu registry (nguyen nhan 1) ---
call :NAP_PATH
where git >nul 2>&1 && exit /b 0

:: --- [3] Do thang thu muc cai mac dinh (nguyen nhan 2 va 3) ---
call :DO_THU_MUC
where git >nul 2>&1 && (
    echo   [OK] Tim thay git san co, khong can cai lai.
    exit /b 0
)

:: --- [4] Chua co that -> tu cai ---
echo.
echo   May chua co git. Dang tu cai, khong can lam gi them...
echo.

:: 4a. winget: nhanh nhat, co san tren Win11 va Win10 ban moi
where winget >nul 2>&1
if not errorlevel 1 (
    echo   [Cach 1] Cai qua winget...
    winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements --silent
    call :NAP_PATH
    call :DO_THU_MUC
    where git >nul 2>&1 && (
        echo   [OK] Da cai git qua winget.
        exit /b 0
    )
    echo   [!] winget khong xong viec, chuyen sang cach 2.
) else (
    echo   [!] May khong co winget, dung cach 2.
)

:: 4b. Tai thang bo cai chinh thuc - day la duong ma ban cu thieu.
::     Nguon: github.com/git-for-windows/git, dung noi winget lay ve.
echo   [Cach 2] Tai bo cai chinh thuc tu github.com/git-for-windows...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {'arm64'} elseif ($env:PROCESSOR_ARCHITECTURE -eq 'x86' -and -not $env:PROCESSOR_ARCHITEW6432) {'32-bit'} else {'64-bit'}; $rel = Invoke-RestMethod 'https://api.github.com/repos/git-for-windows/git/releases/latest' -UseBasicParsing; $a = $rel.assets | Where-Object { $_.name -like ('Git-*-' + $arch + '.exe') } | Select-Object -First 1; if (-not $a) { throw 'khong thay bo cai cho may nay' }; $out = Join-Path $env:TEMP $a.name; Write-Host ('   Dang tai ' + $a.name + ' (' + [math]::Round($a.size/1MB) + ' MB)...'); Invoke-WebRequest $a.browser_download_url -OutFile $out -UseBasicParsing; Write-Host '   Dang cai dat, mat khoang 1-2 phut, dung tat cua so...'; $p = Start-Process $out -ArgumentList '/VERYSILENT','/NORESTART','/NOCANCEL','/SP-' -Wait -PassThru; Remove-Item $out -Force -ErrorAction SilentlyContinue; exit $p.ExitCode } catch { Write-Host ('   [LOI] ' + $_.Exception.Message); exit 1 }"

call :NAP_PATH
call :DO_THU_MUC
where git >nul 2>&1 && (
    echo   [OK] Da cai git.
    exit /b 0
)

:: --- [5] Het cach ---
echo.
echo ============================================================
echo  [LOI] Khong tu cai duoc git tren may nay.
echo ============================================================
echo.
echo   Thuong la do may khong vao duoc mang, hoac bi chan tai file.
echo.
echo   Cach xu ly bang tay:
echo     1. Tai git tai: https://git-scm.com/download/win
echo     2. Cai binh thuong, bam Next het, khong can doi gi.
echo     3. Cai xong DONG HET cua so den roi mo lai file vua bam.
echo        (Cua so cu van giu PATH cu nen se bao thieu git y nguyen.)
echo.
exit /b 1


:: -- Nap lai PATH tu registry --------------------------------
:: Doc ca PATH may (HKLM) lan PATH nguoi dung (HKCU) - git cai kieu
:: per-user chi ghi vao HKCU, bo qua la khong bao gio thay.
:NAP_PATH
set "_SYSPATH="
set "_USRPATH="
for /f "usebackq tokens=2,*" %%A in (`reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul`) do set "_SYSPATH=%%B"
for /f "usebackq tokens=2,*" %%A in (`reg query "HKCU\Environment" /v Path 2^>nul`) do set "_USRPATH=%%B"
if defined _SYSPATH set "PATH=%_SYSPATH%;%PATH%"
if defined _USRPATH set "PATH=%_USRPATH%;%PATH%"
goto :eof


:: -- Do thang cac thu muc git hay nam ------------------------
:DO_THU_MUC
for %%D in (
    "%ProgramFiles%\Git\cmd"
    "%ProgramW6432%\Git\cmd"
    "%ProgramFiles(x86)%\Git\cmd"
    "%LOCALAPPDATA%\Programs\Git\cmd"
    "%USERPROFILE%\AppData\Local\Programs\Git\cmd"
) do if exist "%%~D\git.exe" set "PATH=%%~D;%PATH%"
goto :eof

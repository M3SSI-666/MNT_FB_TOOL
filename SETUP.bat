@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

:: ============================================================
::  MNT FB AutoPost - CAI DAT LAN DAU (bang git)
:: ------------------------------------------------------------
::  CAI TRON GOI - may trang chay MOT file nay la xong. No se:
::    0. Cai Python 3.13 neu chua co (tai tu python.org, cai ngam)
::    1. Cai git neu chua co
::    2. Tai (git clone) toan bo code ve %USERPROFILE%\MNT_FB_TOOL
::    3. Chay INSTALL.bat de cai Python packages + Chromium
::    4. Tao loi tat "MNT FB AutoPost" ngoai Desktop va MO APP
::  Sau nay muon cap nhat: bam nut Cap nhat trong app (hoac UPDATE.bat).
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

:: --- [0] Kiem tra / cai Python ---
:: Ban cu bat may khach tu cai Python truoc (va nho tick "Add Python to PATH"),
:: thieu la INSTALL.bat dung lai. Nay tu cai luon: ban Python.org, cai cho RIENG
:: nguoi dung nay (khong can quyen Admin), tu them vao PATH.
::
:: Phai CHAY THU python chu khong chi "where python": Windows 10/11 co san mot
:: python.exe GIA (App execution alias) trong WindowsApps - goi no chi mo
:: Microsoft Store, khong chay duoc gi. Kiem luon phien ban >= 3.11.
echo [1/4] Kiem tra Python...
call :TIM_PY
if defined PYEXE goto PY_XONG

echo   Chua co Python - dang tu cai Python 3.13 (khong can lam gi, cho chut)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $v='3.13.9'; $u='https://www.python.org/ftp/python/' + $v + '/python-' + $v + '-amd64.exe'; $o=Join-Path $env:TEMP ('python-' + $v + '-amd64.exe'); Write-Host '   Dang tai Python tu python.org ...'; Invoke-WebRequest $u -OutFile $o -UseBasicParsing; Write-Host '   Dang cai Python, mat khoang 1-3 phut, dung tat cua so...'; $p=Start-Process $o -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=1','Include_launcher=0','Include_test=0','Include_doc=0' -Wait -PassThru; Remove-Item $o -Force -ErrorAction SilentlyContinue; exit $p.ExitCode } catch { Write-Host ('   [LOI] ' + $_.Exception.Message); exit 1 }"
call :TIM_PY
if not defined PYEXE (
    echo [LOI] Khong cai duoc Python tu dong.
    echo       Tai va cai thu cong tai: https://www.python.org/downloads
    echo       Nho TICK "Add Python to PATH", cai xong chay lai SETUP.bat.
    pause
    exit /b 1
)

:PY_XONG
:: Dua thu muc Python vua tim len DAU PATH cho ca phien nay: INSTALL.bat goi
:: "python", RUN_APP goi "pythonw" - phai trung dung ban nay, khong phai ban gia
:: trong WindowsApps hay ban cu nao khac.
for %%I in ("!PYEXE!") do set "PYDIR=%%~dpI"
set "PATH=!PYDIR!;!PYDIR!Scripts;%PATH%"
echo [OK] Python san sang: !PYEXE!
echo.

:: --- [1] Kiem tra / cai git ---
:: Viec tim va cai git nam trong _TIM_GIT.bat. Nhung SETUP.bat chay DOC LAP
:: (truoc khi co repo) nen thuong khong co file do nam canh — luc ay tai tam
:: no ve %TEMP% roi goi. Tai ve con hon chep tay logic sang day: hai ban se
:: lech nhau, va ban o SETUP la ban khong ai test.
echo [2/4] Kiem tra git...

:: May da co git roi thi DUNG LAI o day. Thieu buoc nay thi khi tai
:: _TIM_GIT.bat that bai (mang chap chon), script nhay thang sang winget va
:: di cai de len ban git dang chay ngon lanh.
git --version >nul 2>&1
if not errorlevel 1 goto GIT_XONG

:: Chua co git -> muon dung _TIM_GIT.bat. Khong co san canh minh thi tai tam
:: ve %TEMP%. Tai ve con hon chep tay logic sang day: hai ban se lech nhau, va
:: ban o SETUP la ban khong ai test.
set "TIMGIT=%~dp0_TIM_GIT.bat"
if exist "!TIMGIT!" goto GOI_TIMGIT

set "REPO_PATH=%REPO_URL:https://github.com/=%"
set "REPO_PATH=!REPO_PATH:.git=!"
set "RAW=https://raw.githubusercontent.com/!REPO_PATH!/main/_TIM_GIT.bat"
set "TIMGIT=%TEMP%\_TIM_GIT.bat"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest '!RAW!' -OutFile '!TIMGIT!' -UseBasicParsing } catch { exit 1 }"
if not exist "!TIMGIT!" goto CAI_WINGET

:GOI_TIMGIT
call "!TIMGIT!"
if errorlevel 1 (
    pause
    exit /b 1
)
goto GIT_XONG

:CAI_WINGET
:: Khong tai duoc file phu -> thu not cach co san tren may
where winget >nul 2>&1
if errorlevel 1 (
    echo [LOI] May chua co git, va khong tai duoc bo cai tu dong.
    echo       Tai git thu cong tai: https://git-scm.com/download/win
    echo       Cai xong DONG cua so nay roi mo lai SETUP.bat.
    pause
    exit /b 1
)
winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements --silent
for /f "usebackq tokens=2,*" %%A in (`reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul`) do set "SYSPATH=%%B"
set "PATH=!SYSPATH!;%PATH%;%ProgramFiles%\Git\cmd"

:GIT_XONG
git --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Van chua dung duoc git. Dong cua so nay roi mo lai SETUP.bat.
    pause
    exit /b 1
)
echo [OK] git san sang.
echo.

:: --- [2] Tai code ve (git clone) ---
:: Clone vao %USERPROFILE%\MNT_FB_TOOL (VD C:\Users\Ten\MNT_FB_TOOL) - KHONG canh
:: file SETUP.bat nua: file nay thuong nam trong Downloads, con Desktop hay bi
:: OneDrive dong bo (profiles\ ghi lien tuc hang GB). Mo app bang loi tat Desktop.
cd /d "%USERPROFILE%"

:: TH1: dang dung o BAN DA GIAI NEN san (canh SETUP.bat co luon server.py).
::      Khong can clone gi ca - chay INSTALL.bat ngay tai cho.
if exist "%~dp0server.py" (
    echo [3/4] Da co san ma nguon ngay tai thu muc nay - bo qua tai ve.
    echo.
    echo       [Luu y] Ban dang dung ban GIAI NEN tu file .zip.
    echo               Ban nay KHONG tu cap nhat duoc ^(UPDATE.bat se bao loi^).
    echo               Muon nhan ban moi tu dong: chep rieng SETUP.bat sang
    echo               MOT THU MUC TRONG roi chay o do.
    set "DICH=%~dp0"
    goto :caidat
)

:: TH2: da clone tu truoc (co .git) -> giu nguyen, khong dong vao.
if exist "MNT_FB_TOOL\.git" (
    echo [3/4] Da cai tu truoc o thu muc MNT_FB_TOOL - bo qua tai ve.
    echo       Muon cap nhat len ban moi: bam nut Cap nhat trong app.
    set "DICH=%USERPROFILE%\MNT_FB_TOOL"
    goto :caidat
)

:: TH3: thu muc MNT_FB_TOOL da ton tai nhung KHONG phai repo git.
::      git clone se bao "already exists and is not an empty directory".
::      Thuong do lan cai truoc bi ngat giua chung, hoac da giai nen zip vao day.
if exist "MNT_FB_TOOL" (
    dir /a /b "MNT_FB_TOOL" 2>nul | findstr "." >nul
    if not errorlevel 1 (
        if exist "MNT_FB_TOOL\server.py" (
            echo [3/4] Thu muc MNT_FB_TOOL da co san ma nguon - bo qua tai ve.
            set "DICH=%USERPROFILE%\MNT_FB_TOOL"
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

echo [3/4] Dang tai code ve...
git clone "%REPO_URL%" MNT_FB_TOOL
if errorlevel 1 (
    echo [LOI] Tai code that bai. Kiem tra:
    echo       - Ket noi mang
    echo       - Link repo dung va dang o che do PUBLIC
    pause
    exit /b 1
)
echo [OK] Da tai xong.
set "DICH=%USERPROFILE%\MNT_FB_TOOL"

:caidat
:: %~dp0 luon ket thuc bang dau \, de nguyen thi cd /d "...\" hong va moi lenh
:: sau do chay sai thu muc. Cat dau \ cuoi truoc khi dung.
if "!DICH:~-1!"=="\" set "DICH=!DICH:~0,-1!"
echo.

:: --- [3] Chay INSTALL.bat (Python packages + Chromium) ---
echo [4/4] Dang cai dat moi truong (co the mat vai phut)...
cd /d "!DICH!"
if exist "!DICH!\INSTALL.bat" (
    call "!DICH!\INSTALL.bat" tu_dong
    if errorlevel 1 exit /b 1
) else (
    echo [LOI] Khong tim thay INSTALL.bat trong "!DICH!".
    pause
    exit /b 1
)

echo.
:: --- [4] Loi tat Desktop + mo app ---
:: GetFolderPath('Desktop') tra dung Desktop ke ca khi bi OneDrive doi cho.
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'MNT FB AutoPost.lnk')); $s.TargetPath='!DICH!\RUN_APP.bat'; $s.WorkingDirectory='!DICH!'; $s.IconLocation='!DICH!\static\mnt.ico'; $s.WindowStyle=7; $s.Save(); Write-Host '[OK] Da tao loi tat MNT FB AutoPost ngoai Desktop.' } catch { Write-Host '[Chu y] Khong tao duoc loi tat Desktop - mo app bang RUN_APP.bat.' }"

echo.
echo ============================================================
echo  Cai dat hoan tat - dang mo phan mem...
echo.
echo  Lan sau mo app: bam loi tat "MNT FB AutoPost" ngoai Desktop
echo  (thu muc cai: !DICH!)
echo  Cap nhat ban moi: bam nut Cap nhat trong app.
echo  Lan dau mo app se tu tai Chromium (~680 MB) - cho thanh tien do chay xong.
echo ============================================================
start "" "!DICH!\RUN_APP.bat"
timeout /t 20
exit /b 0

:: ------------------------------------------------------------
:: TIM_PY: dat PYEXE = duong dan python.exe CHAY THAT, ban >= 3.11. Khong thay
:: thi de trong. Thu PATH truoc, roi cac cho python.org hay cai vao.
:TIM_PY
set "PYEXE="
for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined PYEXE (
        "%%P" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PYEXE=%%P"
    )
)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*") do (
    if not defined PYEXE if exist "%%~D\python.exe" (
        "%%~D\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PYEXE=%%~D\python.exe"
    )
)
exit /b 0

@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

:: ============================================================
::  MNT FB AutoPost - CAP NHAT phien ban moi nhat
:: ------------------------------------------------------------
::  Client chi can BAM DUP file nay. No se:
::    1. Kiem tra / cai git neu chua co
::    2. Tat app dang chay (server + runner nen)
::    3. Tai code moi nhat tu GitHub (git pull)
::       -> KHONG dung vao data\ cookies\ profiles\ (da .gitignore)
::    4. Cai them thu vien neu requirements.txt doi
::    5. Mo lai app -> db.py tu nang cap schema
::  DU LIEU (tai khoan, cookie, lich, profile) GIU NGUYEN.
:: ============================================================

echo ============================================================
echo  MNT FB AutoPost - Cap nhat phien ban moi nhat
echo ============================================================
echo.

:: Link repo GitHub - phai KHOP voi SETUP.bat (dong "set REPO_URL=...").
:: Doi repo thi sua ca hai noi. URL gan nhu co dinh nen chap nhan trung.
set "REPO_URL=https://github.com/M3SSI-666/MNT_FB_TOOL.git"

:: --- [0] Neu chua phai thu muc git thi TU GAN GIT vao tai cho ---
:: Ban giai nen tu ZIP khong co .git -> truoc day UPDATE.bat bao loi va dung.
:: Gio: neu thieu .git thi khoi tao repo ngay tai thu muc nay (KHONG xoa file),
:: keo code moi nhat tu GitHub ve. Du lieu ca nhan (data\ cookies\ profiles\...)
:: nam trong .gitignore nen reset --hard KHONG dong toi -> an toan.
if not exist ".git" (
    echo [0/5] Chua phai thu muc git - dang gan git va lay code moi...

    :: Phai co git truoc da. _TIM_GIT.bat co san trong goi ZIP.
    call "%~dp0_TIM_GIT.bat"
    if errorlevel 1 (
        pause
        exit /b 1
    )
    git --version >nul 2>&1
    if errorlevel 1 (
        echo [LOI] Van chua dung duoc git. Dong cua so nay roi bam lai UPDATE.bat.
        pause
        exit /b 1
    )

    :: Khoi tao repo tai cho. git init KHONG xoa file dang co - chi tao .git\.
    git init >nul 2>&1
    git remote add origin "%REPO_URL%" >nul 2>&1
    :: Neu remote da ton tai (lan truoc chay do giua chung) thi cap nhat lai URL.
    git remote set-url origin "%REPO_URL%" >nul 2>&1

    echo       Dang tai code moi nhat tu GitHub...
    git fetch origin >nul 2>&1
    if errorlevel 1 (
        echo [LOI] Khong tai duoc code tu GitHub. Kiem tra ket noi mang roi thu lai.
        pause
        exit /b 1
    )
    :: reset --hard: ghi de file CODE bang ban GitHub. File bi .gitignore
    :: (data\ cookies\ profiles\ backup\ logs\) KHONG bi dong toi.
    git reset --hard origin/main
    if errorlevel 1 (
        echo [LOI] Khong dat duoc code ve ban GitHub. Chup man hinh nay va lien he ho tro.
        pause
        exit /b 1
    )
    :: QUAN TRONG: git init tao nhanh mac dinh ten "master", nhung repo tren
    :: GitHub dung "main". Neu de nguyen, lan UPDATE sau buoc [3] doc ten nhanh
    :: ra "master" roi "git reset --hard origin/master" -> LOI unknown revision.
    :: Tao han nhanh "main" bam vao origin/main de cac lan sau chay tron.
    git checkout -B main --track origin/main >nul 2>&1
    echo [OK] Da gan git xong. Tiep tuc cap nhat binh thuong.
    echo.
)

:: --- [1] Kiem tra git, tu cai neu thieu ---
:: Toan bo viec tim va cai git nam trong _TIM_GIT.bat (xem giai thich trong do).
:: Ban cu chi thu moi "git --version" roi doi hoi winget, thieu winget la bo
:: cuoc — nen may khong co winget khong bao gio update duoc.
echo [1/6] Kiem tra git...
call "%~dp0_TIM_GIT.bat"
if errorlevel 1 (
    pause
    exit /b 1
)
:: Tu kiem lai chu khong tin moi ma tra ve: neu vi ly do nao do git van chua
:: goi duoc thi bao ngay o day, con hon de buoc [3] chet giua chung sau khi
:: app da bi tat.
git --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Van chua dung duoc lenh git.
    echo       Dong cua so nay roi bam lai UPDATE.bat.
    pause
    exit /b 1
)
echo [OK] git san sang.
echo.

:: --- [2] Tat app dang chay (giong RESTART.bat) ---
echo [2/6] Dang tat app dang chay...
:: Kill Flask server (:8080) - KHONG dung /T de tranh diet chrome.exe con
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
:: Kill orphan scheduler.py + join_groups_worker.py (python.exe / pythonw.exe)
powershell -NoProfile -NonInteractive -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and ($_.CommandLine -like '*scheduler.py*' -or $_.CommandLine -like '*join_groups_worker*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
ping -n 3 127.0.0.1 >nul
echo.

:: --- [3a] SAO LUU DU LIEU truoc khi dong vao code ---
:: Migration cua phan mem nay co XOA that (accounts.comment_bai,
:: comment_posts.nhom_url, content.link_anh_hook) va co DOI that
:: (loai_dang C_Home -> X_Home). Chung chi chay MOT CHIEU, khong co duong nguoc.
:: Nen ban sao nay la thu duy nhat cuu duoc du lieu khi mot ban cap nhat hong,
:: hoac khi phai lui ve ban cu.
echo [3/6] Sao luu du lieu...
set "SAOLUU=%LOCALAPPDATA%\MNT FB AutoPost\backup"
if not exist "!SAOLUU!" mkdir "!SAOLUU!" >nul 2>&1
for /f "tokens=1-6 delims=/: " %%a in ("%date% %time%") do set "DAU=%%c%%b%%a_%%d%%e"
set "DAU=!DAU: =0!"
if exist "data\app.db" (
    copy /y "data\app.db" "!SAOLUU!\app_!DAU!.db" >nul 2>&1
    if errorlevel 1 (
        echo [LOI] Khong sao luu duoc du lieu - DUNG LAI de khong lam mat gi.
        echo       Kiem tra quyen ghi vao: !SAOLUU!
        pause
        exit /b 1
    )
    echo [OK] Da sao luu: !SAOLUU!\app_!DAU!.db
) else (
    echo      (chua co du lieu - bo qua sao luu)
)
:: Giu 10 ban gan nhat, xoa bot cho khoi phinh o dia.
for /f "skip=10 delims=" %%f in ('dir /b /o-d "!SAOLUU!\app_*.db" 2^>nul') do del "!SAOLUU!\%%f" >nul 2>&1
echo.

:: --- [3b] Tai code theo TAG PHAT HANH ---
:: KHONG dung dau nhanh main: dau main la commit MOI NHAT tac gia vua day len,
:: co the la code dang sua do. Tag la diem da duoc chu dong tuyen bo phat hanh.
::
::   UPDATE.bat            -> len tag moi nhat
::   UPDATE.bat v1.0.1     -> ghim ve dung ban do
echo [4/6] Dang tai code tu GitHub...
git fetch --tags --force origin >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tai duoc tu GitHub. Kiem tra ket noi mang roi thu lai.
    pause
    exit /b 1
)

set "DICH=%~1"
if "!DICH!"=="" (
    :: Tag moi nhat theo NGAY TAO, khong phai theo thu tu chu cai:
    :: sap theo chu cai thi v1.10.0 dung truoc v1.9.0.
    for /f "delims=" %%t in ('git tag --sort^=-creatordate 2^>nul') do (
        if "!DICH!"=="" set "DICH=%%t"
    )
)
if "!DICH!"=="" (
    echo [LOI] Kho code chua co ban phat hanh nao ^(chua gan tag^).
    echo       Lien he nguoi cung cap phan mem.
    pause
    exit /b 1
)

git rev-parse "!DICH!" >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay phien ban "!DICH!".
    echo       Cac ban dang co:
    git tag --sort^=-creatordate
    pause
    exit /b 1
)

echo      Cap nhat len: !DICH!
git reset --hard "!DICH!"
if errorlevel 1 (
    echo [LOI] Dat code ve ban "!DICH!" that bai.
    pause
    exit /b 1
)
echo.

:: --- [4] Cai them thu vien neu doi ---
echo [5/6] Kiem tra thu vien Python...
pip install -r requirements.txt --disable-pip-version-check -q
if errorlevel 1 (
    echo [Chu y] Cai thu vien co van de - app van co the chay voi thu vien cu.
)
echo.

:: --- [5] Mo lai app ---
echo [6/6] Dang mo lai app...
call "%~dp0_TIM_PYTHON.bat"
if errorlevel 1 exit /b 1
start "" %PYW% -X utf8 server.py

echo.
echo ============================================================
if exist "version.txt" (
    set /p VER=<version.txt
    echo  HOAN TAT - da cap nhat len phien ban: !VER!
) else (
    echo  HOAN TAT - da cap nhat phien ban moi nhat.
)
echo  Du lieu cua ban duoc giu nguyen.
echo ============================================================
echo.
echo  (Cua so nay tu dong dong sau 5 giay)
ping -n 6 127.0.0.1 >nul
exit

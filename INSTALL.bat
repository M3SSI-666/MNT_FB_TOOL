@echo off
echo ============================================================
echo  MNT FB AutoPost - Cai dat lan dau
echo ============================================================
echo.

:: Kiem tra Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Chua cai Python!
    echo Vui long tai va cai Python 3.11+ tu: https://python.org
    echo Nho tick "Add Python to PATH" khi cai dat.
    pause
    exit /b 1
)

echo [OK] Python da co san:
python --version
echo.

:: Cai packages
echo [1/3] Dang cai Python packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo [LOI] Cai packages that bai!
    pause
    exit /b 1
)
echo.

:: Cai Playwright browser
echo [2/3] Dang cai Chromium browser cho Playwright...
playwright install chromium
if errorlevel 1 (
    echo [LOI] Cai Playwright that bai!
    pause
    exit /b 1
)
echo.

:: Cai Tailscale (de dieu khien tu xa qua dien thoai / may khac)
echo [3/3] Dang cai Tailscale (dieu khien tu xa)...
where winget >nul 2>&1
if errorlevel 1 (
    echo [Chu y] May nay khong co winget.
    echo         Hay tai Tailscale thu cong tai: https://tailscale.com/download/windows
) else (
    winget install --id Tailscale.Tailscale -e --accept-package-agreements --accept-source-agreements --silent
    if errorlevel 1 (
        echo [Chu y] Cai Tailscale chua chac xong ^(co the can quyen admin, hoac da cai san^).
        echo         Neu can, tai thu cong tai: https://tailscale.com/download/windows
    ) else (
        echo [OK] Da cai Tailscale.
    )
)
echo.

echo ============================================================
echo  Cai dat hoan tat!
echo.
echo  BUOC CUOI (lam tay 1 lan):
echo   1. Mo Tailscale, dang nhap bang tai khoan Google
echo      -- dung CUNG tai khoan voi cac may/dien thoai khac.
echo   2. Chay RUN_APP.bat de khoi dong phan mem.
echo   3. Vao tab "Hanh dong" -^> dat mat khau truy cap tu xa.
echo   (Tuy chon) Chay INSTALL_AUTOSTART.bat de app tu chay khi mo may.
echo ============================================================
pause

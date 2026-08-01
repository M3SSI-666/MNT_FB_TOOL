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
echo [1/2] Dang cai Python packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo [LOI] Cai packages that bai!
    pause
    exit /b 1
)
echo.

:: Cai Playwright browser
echo [2/2] Dang cai Chromium browser cho Playwright...
playwright install chromium
if errorlevel 1 (
    echo [LOI] Cai Playwright that bai!
    pause
    exit /b 1
)
echo.

echo ============================================================
echo  Cai dat hoan tat!
echo.
echo  BUOC CUOI:
echo   1. Chay RUN_APP.bat de khoi dong phan mem.
echo   (Tuy chon) Chay INSTALL_AUTOSTART.bat de app tu chay khi mo may.
echo ============================================================
pause

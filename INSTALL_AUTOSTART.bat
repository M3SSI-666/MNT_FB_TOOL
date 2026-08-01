@echo off
cd /d "%~dp0"
echo ============================================================
echo  Cai dat: TU DONG chay nen khi mo may (dang nhap Windows)
echo ============================================================
echo.

schtasks /Create /TN "MNT_AutoPost" /TR "\"%~dp0START_BACKGROUND.bat\"" /SC ONLOGON /RL HIGHEST /F
if errorlevel 1 (
    echo.
    echo [LOI] Khong tao duoc tac vu. Thu chay file nay bang quyen Administrator.
    pause
    exit /b 1
)

echo.
echo [OK] Da dang ky. Tu lan mo may sau, phan mem se tu chay nen.
echo      - Bang dieu khien: http://localhost:8080
echo      - Go bo tu dong chay: chay UNINSTALL_AUTOSTART.bat
echo.
echo  Muon chay ngay bay gio ma khong can khoi dong lai:
echo      chay START_BACKGROUND.bat
pause

@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

rem ============================================================
rem  MNT FB AutoPost - KHOI PHUC DU LIEU tu ban sao luu
rem ------------------------------------------------------------
rem  Dung khi mat du lieu: o cung hong, lo tay xoa, hoac cap nhat
rem  xong thi du lieu sai.
rem
rem  Nhan ca hai loai file:
rem    - app_*.db          ban tren may (khong can mat khau)
rem    - MNT_*.db.enc      ban tai tu Telegram (can mat khau)
rem
rem  KHONG dung file nay de sua loi cap nhat - do la KHOI_PHUC.bat.
rem ============================================================

cd /d "%~dp0"

echo.
echo  Dang dong phan mem truoc khi khoi phuc...
rem Thay file CSDL duoi chan phan mem dang chay thi hai ben ghi de
rem len nhau, hong ca hai. Dong truoc cho chac.
taskkill /f /im pythonw.exe >nul 2>&1
taskkill /f /im server.exe  >nul 2>&1
timeout /t 2 /nobreak >nul

call "%~dp0_TIM_PYTHON.bat"
if not defined PY (
    echo  [LOI] Khong tim thay Python.
    pause
    exit /b 1
)

%PY% -X utf8 "%~dp0sao_luu.py" --khoi-phuc
set "MA=!errorlevel!"

echo.
pause
exit /b !MA!

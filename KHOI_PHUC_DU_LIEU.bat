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
rem CHI dong CHINH phan mem nay: server dang nghe cong 8080 + runner giu
rem khoa trong thu muc nay (dung_het.py). KHONG taskkill /im pythonw.exe:
rem may co the chay song song Scale Tool, diet theo ten la diet luon no.
call "%~dp0_TIM_PYTHON.bat"
if not defined PY (
    echo  [LOI] Khong tim thay Python.
    pause
    exit /b 1
)
set SV_PID=
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING 2^>nul') do call set SV_PID=%%SV_PID%% %%a
%PY% -X utf8 "%~dp0dung_het.py" %SV_PID%
timeout /t 2 /nobreak >nul

%PY% -X utf8 "%~dp0sao_luu.py" --khoi-phuc
set "MA=!errorlevel!"

echo.
pause
exit /b !MA!

@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

rem ============================================================
rem  MNT FB AutoPost - CAI LICH DANH THUC MAY
rem ------------------------------------------------------------
rem  Chay MOT LAN. Sau do Windows se tu danh thuc may dung gio
rem  sang da dat trong phan mem (tab Hanh dong > Lich cua may).
rem
rem  CHI CO TAC DUNG khi may NGU DONG hoac NGU. May TAT HAN thi
rem  dien da ngat, khong phan mem nao bat len duoc - luc do phai
rem  vao BIOS bat RTC Alarm.
rem ============================================================

cd /d "%~dp0"

echo.
echo ============================================================
echo  Cai lich danh thuc may
echo ============================================================
echo.

rem Doc gio sang tu chinh co so du lieu cua phan mem, de khong phai
rem dien lai o hai noi roi lech nhau.
call "%~dp0_TIM_PYTHON.bat"
if not defined PY (
    echo  [LOI] Khong tim thay Python.
    pause
    exit /b 1
)

for /f "delims=" %%g in ('%PY% -X utf8 -c "import db;print(db.get_setting('lm_gio_bat','07:00'))" 2^>nul') do set "GIO=%%g"
if "!GIO!"=="" set "GIO=07:00"
echo  Gio danh thuc lay tu phan mem: !GIO!
echo.

rem 1. Cho phep hen gio danh thuc. Windows mac dinh TAT muc nay tren
rem    may laptop, va tat thi tac vu ben duoi khong bao gio danh thuc noi.
echo  [1/3] Bat "cho phep hen gio danh thuc"...
powercfg -setacvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 1 >nul 2>&1
powercfg -setdcvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 1 >nul 2>&1
powercfg -setactive SCHEME_CURRENT >nul 2>&1
echo        OK

rem 2. Bat ngu dong. Nhieu may Windows 10/11 tat san tinh nang nay.
echo  [2/3] Bat che do ngu dong...
powercfg /hibernate on >nul 2>&1
echo        OK

rem 3. Dang ky tac vu danh thuc. Dung PowerShell chu khong dung schtasks:
rem    schtasks khong co co "danh thuc may de chay", ma do lai chinh la
rem    thu duy nhat can o day.
echo  [3/3] Dang ky tac vu danh thuc luc !GIO!...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$a = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c exit';" ^
  "$t = New-ScheduledTaskTrigger -Daily -At '!GIO!';" ^
  "$s = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries;" ^
  "Register-ScheduledTask -TaskName 'MNT_DanhThucMay' -Action $a -Trigger $t -Settings $s -Force | Out-Null" 2>nul

if errorlevel 1 (
    echo.
    echo  [LOI] Khong dang ky duoc tac vu.
    echo        Bam chuot phai file nay va chon "Run as administrator".
    pause
    exit /b 1
)

echo        OK
echo.
echo ============================================================
echo  XONG. May se tu thuc day luc !GIO! moi ngay.
echo ============================================================
echo.
echo  Kiem tra: mo Task Scheduler, tim "MNT_DanhThucMay".
echo  Go bo   : chay lenh
echo            schtasks /Delete /TN "MNT_DanhThucMay" /F
echo.
echo  LUU Y: neu trong phan mem ban doi GIO SANG, hay chay lai file nay.
echo.
pause

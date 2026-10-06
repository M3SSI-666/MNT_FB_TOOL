@echo off
echo ============================================================
echo  Dang tat toan bo server + scheduler cu...
echo ============================================================

:: Tim PID server dang giu cong 8080 (netstat nhanh, khong treo)
set SV_PID=
:: GOM HET, khong chi lay dong cuoi. Ngay 19/09 co HAI server cung nghe cong
:: 8080 (PID 13680 tu 15:07 va PID 21480 tu 21:34): lan truoc diet truot cai cu
:: ma cai moi van bind duoc vi Flask bat SO_REUSEADDR. Vong lap cu chi giu dong
:: CUOI nen se diet nham cai vua khoi dong, con cai cu song tiep.
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING 2^>nul') do call set SV_PID=%%SV_PID%% %%a

:: Dung server + runner bang dung_het.py.
::
:: KHONG dung taskkill va KHONG quet Get-CimInstance nua. Do tren may that ngay
:: 19/09: taskkill /F /PID <server> TREO (cua so cmd dung im o dong "Kill Flask
:: server PID ..."), taskkill /F /T /PID <runner> treo >20s ma tien trinh van
:: song, con Get-CimInstance loc theo CommandLine thi 30s chua xong luc may tai
:: nang. Ca ba deu phai duyet tien trinh cua CA MAY qua RPC/WMI.
::
:: dung_het.py chup mot anh danh sach tien trinh roi goi thang TerminateProcess:
:: cung phep do do, chet trong 0,00 giay. No con tim runner qua FILE KHOA nen
:: khong phu thuoc file pid con hay mat.
echo  Dang dung server + runner...
call "%~dp0_TIM_PYTHON.bat"
if errorlevel 1 exit /b 1
%PY% -X utf8 "%~dp0dung_het.py" %SV_PID%

call :cho 2

echo  Khoi dong lai MNT FB AutoPost (cua so app)...
cd /d "%~dp0"
:: Mo lai cua so app (pywebview). Server cu da bi kill o tren nen cua so cu
:: da dong; lenh nay mo cua so moi voi code moi.
call "%~dp0_TIM_PYTHON.bat"
if errorlevel 1 exit /b 1
start "" %PYW% -X utf8 server.py
exit

:: ============================================================
:: :cho <so giay> - ngu mot lat. KHONG dung ping.exe nua.
::
:: Loi gap tren may that ngay 06/10: chay cap nhat thi bat hop thoai
::   "PING.EXE - Application Error - The application was unable to start
::    correctly (0xc0000142)"
:: Hop thoai do CHAN, phai bam OK moi di tiep, nen ban cap nhat dung han.
::
:: 0xc0000142 nghia la tien trinh KHONG KHOI TAO DUOC. Luc chay cap nhat may
:: dang co hang tram tien trinh Chromium cua cac phien dang bai, nen tao them
:: bat ky exe nao cung co the truot. ping.exe o day chi de DEM GIO, khong lien
:: quan gi toi mang - mot viec vat ma lam hong ca ban cap nhat.
::
:: Nay dung Python da tim duoc o tren: no vua chay xong ngay truoc do nen chac
:: chan khoi dong duoc, va khong phai goi them exe he thong nao.
:: ============================================================
:cho
if not defined PY goto cho_lui
%PY% -c "import time,sys;time.sleep(float(sys.argv[1]))" %1 >nul 2>&1
if not errorlevel 1 exit /b 0
:cho_lui
:: KHONG dung `timeout` lam duong lui: no bao "Input redirection is not
:: supported" roi thoat ngay khi stdin bi chuyen huong - da do that, bao cho
:: 1 giay ma chi ton 0,02 giay. PowerShell thi chiu duoc.
powershell -NoProfile -NonInteractive -Command "Start-Sleep -Seconds %1" >nul 2>&1
exit /b 0

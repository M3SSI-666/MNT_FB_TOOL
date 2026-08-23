@echo off
:: ============================================================
::  Tim trinh chay Python va dat vao bien PYW.
::  File nay duoc CALL tu RUN_APP / RESTART / START_BACKGROUND / UPDATE.
:: ------------------------------------------------------------
::  Vi sao can: tren may moi, "pythonw" thuong KHONG co trong PATH
::  (cai Python tu Microsoft Store, hoac quen tick "Add Python to
::  PATH" luc cai). Goi thang pythonw se bao:
::     Windows cannot find 'pythonw'
::  Thu lan luot: pythonw -> pyw -> python -> py -3
::  Hai cai cuoi co hien cua so den nhung van chay duoc.
:: ============================================================

:: BAN CAI DAT: Python di kem nam ngay trong thu muc, o python\. Phai uu tien
:: no truoc moi thu khac. Ca diem cua ban cai la khach KHONG phai cai Python,
:: nen tim Python cua he thong la tim mot thu khong ton tai - hoac te hon, tim
:: thay mot ban Python khac khong co thu vien nao cua phan mem nay.
:: Dat DAU NHAY KEP vao trong bien luon. Thu muc cai mac dinh la
::   %LOCALAPPDATA%\Programs\MNT FB AutoPost
:: co dau cach, nen "start "" %PYW% ..." khong co nhay kep se dut doi o chu
:: "MNT" va Windows di tim mot chuong trinh ten "C:\...\MNT".
:: Khong dung set "PYW=..." o day duoc: kieu do se an mat cap nhay kep.
:: Cac nhanh duoi khong can nhay kep, va "py -3" thi TUYET DOI khong duoc boc
:: nhay kep vi no la hai tu.
set "PYW="
set "PY="
if exist "%~dp0python\pythonw.exe" (
    set PYW="%~dp0python\pythonw.exe"
    set PY="%~dp0python\python.exe"
    goto :TIM_XONG
)

where pythonw >nul 2>&1 && set "PYW=pythonw"
if not defined PYW ( where pyw    >nul 2>&1 && set "PYW=pyw" )
if not defined PYW ( where python >nul 2>&1 && set "PYW=python" )
if not defined PYW ( where py     >nul 2>&1 && set "PYW=py -3" )

:: PY = ban CO cua so den. Dung cho viec phai CHO CHAY XONG roi doc ket qua,
:: nhu chay bai kiem trong PHAT_HANH.bat. Khong dung PYW o do duoc: pythonw la
:: chuong trinh dang GUI, cmd goi xong la tra ve ngay khong doi, nen errorlevel
:: luon bang 0 - cong chan se luon "qua" du bai kiem truot.
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY ( where py >nul 2>&1 && set "PY=py -3" )

if not defined PYW (
    echo.
    echo ============================================================
    echo  [LOI] Khong tim thay Python tren may nay.
    echo ============================================================
    echo.
    echo   Cach xu ly:
    echo     1. Tai Python 3.11 tro len tai: https://python.org/downloads
    echo     2. Khi cai, NHO TICK o "Add Python to PATH" ngay man hinh dau.
    echo     3. Cai xong: dong het cua so den, chay INSTALL.bat,
    echo        roi mo lai file vua bam.
    echo.
    echo   Neu da cai Python roi ma van bao loi: rat co the ban cai tu
    echo   Microsoft Store. Hay go di va cai lai ban tai tu python.org.
    echo.
    pause
    exit /b 1
)

:TIM_XONG
exit /b 0

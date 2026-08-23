@echo off
echo ============================================================
echo  Go bo: TU DONG chay nen khi mo may
echo ============================================================
echo.

schtasks /Delete /TN "MNT_AutoPost" /F
if errorlevel 1 (
    echo [Chu y] Khong tim thay tac vu ^(co the chua cai, hoac da go^).
) else (
    echo [OK] Da go. Phan mem se KHONG con tu chay khi mo may.
)
echo.
pause

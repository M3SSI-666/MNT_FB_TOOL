@echo off
cd /d "%~dp0"

:: ============================================================
::  MNT FB AutoPost — chay NEN (khong cua so, khong CMD)
::  Server lang nghe :8080 de dieu khien tu xa qua Tailscale.
::  Dung lai: bam "Tat phan mem" trong bang dieu khien.
:: ============================================================

start "" pythonw -X utf8 server.py --no-browser

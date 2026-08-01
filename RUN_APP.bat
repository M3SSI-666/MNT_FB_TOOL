@echo off
cd /d "%~dp0"

:: ============================================================
::  MNT FB AutoPost — mo CUA SO APP (pywebview, khong hien CMD)
::  Nhan X de dong app se tat sach: server + runner dang nen.
:: ============================================================

start "" pythonw -X utf8 server.py

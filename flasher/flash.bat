@echo off
chcp 65001 >nul
title 5v5 FLASHER - STATION MODE (colok-cabut otomatis)
cd /d "%~dp0"

echo.
echo  ==========================================================
echo   5v5 FLASHER  -  STATION MODE
echo   Colok modem -^> proses otomatis -^> cabut -^> colok lagi
echo.
echo   Catatan: kalau GUI/web modem TIDAK bisa dibuka setelah
echo   equipmode, itu NORMAL (modem sedang equip mode = web mati).
echo   Tool ini menunggu lewat telnet, bukan web.
echo.
echo   Tekan Ctrl+C kapan saja untuk berhenti.
echo  ==========================================================
echo.

python flasher.py batch
set RC=%ERRORLEVEL%

echo.
echo  Selesai (exit code %RC%).
pause

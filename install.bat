@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo  5v5 FLASHER - pemasangan (Windows)
echo  Folder: %CD%
echo.

rem ---------------------------------------------------------------- 1. Python
set "PY="
where py >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>&1
    if not errorlevel 1 set "PY=python"
)

if not defined PY (
    echo   [FAIL] Python tidak ditemukan.
    echo          Pasang Python 3.8+ dari: https://www.python.org/downloads/windows/
    echo          Centang "Add python.exe to PATH", atau jalankan:
    echo              winget install -e --id Python.Python.3.12
    echo.
    pause
    exit /b 1
)

echo   [ OK ] Python:
%PY% --version

rem ------------------------------------------------------------------- 2. pip
%PY% -m pip --version >nul 2>&1
if errorlevel 1 (
    echo   [ .. ] pip belum ada - mencoba ensurepip...
    %PY% -m ensurepip --upgrade >nul 2>&1
)

%PY% -m pip --version >nul 2>&1
if errorlevel 1 (
    echo   [ !! ] pip tidak tersedia.
    echo          Tidak masalah - tool ini tidak butuh dependensi apa pun.
) else (
    echo   [ OK ] pip siap
    echo   [ .. ] memasang paket proyek dan pytest...
    %PY% -m pip install --quiet -e . >nul 2>&1
    %PY% -m pip install --quiet -r requirements-dev.txt >nul 2>&1
)

rem ------------------------------------------------------------ 3. uji  cepat
echo.
echo   [ .. ] uji cepat...
%PY% flasher\flasher.py --plain --help >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] flasher.py gagal dijalankan.
    echo          Coba jalankan manual: %PY% flasher\flasher.py --help
    echo.
    pause
    exit /b 1
)
echo   [ OK ] flasher.py jalan

%PY% -c "import pytest" >nul 2>&1
if errorlevel 1 (
    echo   [ .. ] pytest tidak ada - lewati uji otomatis
) else (
    %PY% -m pytest -q >nul 2>&1
    if errorlevel 1 (
        echo   [ !! ] ada uji yang gagal - jalankan: %PY% -m pytest -q
    ) else (
        echo   [ OK ] uji otomatis lolos
    )
)

echo.
echo   Selesai.
echo.
echo   Langkah berikutnya - colok ONT Huawei ke LAN,
echo   laptop di 192.168.100.2 atau 192.168.18.2 /24:
echo.
echo       %PY% flasher\flasher.py detect       - cek modem terdeteksi
echo       %PY% flasher\flasher.py batch        - MODE STASIUN otomatis
echo.
echo   Atau dobel-klik: flasher\flash.bat
echo   Firmware .bin ditaruh di folder flasher\
echo   Detail lengkap: flasher\README.md
echo.
pause

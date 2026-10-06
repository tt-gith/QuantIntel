@echo off
setlocal
cd /d "%~dp0"
echo === Quant Intelligence Network - Kurulum ===
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [HATA] Python bulunamadi.
    echo python.org/downloads adresinden Python 3.10 veya ustunu kurun.
    echo Kurulumda "Add python.exe to PATH" kutusunu isaretlemeyi unutmayin.
    pause
    exit /b 1
)

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo [HATA] Python 3.10 veya ustu gerekli. Mevcut surum:
    %PY% --version
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Sanal ortam olusturuluyor...
    %PY% -m venv .venv || (echo [HATA] venv olusturulamadi & pause & exit /b 1)
)

echo Paketler kuruluyor...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q || (echo [HATA] Paket kurulumu basarisiz & pause & exit /b 1)

echo.
echo Ilk veri cekme ve ozet olusturma (1-2 dakika surebilir)...
".venv\Scripts\python.exe" run.py weekly

echo.
echo === Kurulum tamam ===
echo Siteyi acmak icin: site_ac.bat
echo Otomatik calisma icin simdi gorev_kur.bat dosyasini calistirin.
echo.
pause

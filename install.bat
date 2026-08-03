@echo off
echo Clipboard AI — Kurulum
echo ========================
echo.

:: Python kontrolü
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi. https://python.org adresinden indirin.
    pause
    exit /b 1
)

echo [1/2] Bagimlilıklar kuruluyor...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [HATA] pip install basarisiz oldu.
    pause
    exit /b 1
)

echo [2/2] Kurulum tamamlandi.
echo.
echo Baslat: python monitor.py
echo      veya: build_exe.bat ile tek .exe dosyası olusturun
echo.
pause

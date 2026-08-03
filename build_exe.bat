@echo off
echo Clipboard AI — EXE Olusturuluyor
echo ==================================
echo.

pyinstaller ^
    --onefile ^
    --noconsole ^
    --name "ClipboardAI" ^
    monitor.py

if errorlevel 1 (
    echo [HATA] Build basarisiz.
    pause
    exit /b 1
)

echo.
echo [OK] dist\ClipboardAI.exe olusturuldu.
echo Cift tiklayarak calistirabilirsiniz.
echo.
pause

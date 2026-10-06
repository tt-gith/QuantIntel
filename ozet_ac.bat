@echo off
if exist "%~dp0digests\latest.html" (
    start "" "%~dp0digests\latest.html"
) else (
    echo Henuz ozet yok. Once kurulum.bat veya "qin weekly" calistirin.
    pause
)

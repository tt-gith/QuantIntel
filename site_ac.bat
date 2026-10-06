@echo off
rem Siteyi bu bilgisayarda acar (tarayici kendiliginden acilir). Kapatmak icin bu pencereyi kapatin.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Once kurulum.bat calistirin.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" run.py serve
pause

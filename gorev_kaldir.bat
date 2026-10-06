@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "Unregister-ScheduledTask -TaskName 'QuantIntel - Gunluk Cekme' -Confirm:$false -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName 'QuantIntel - Haftalik Ozet' -Confirm:$false -ErrorAction SilentlyContinue; Write-Host 'Gorevler kaldirildi.'"
pause

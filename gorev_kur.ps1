# Quant Intelligence Network - Windows Gorev Zamanlayici kaydi
# 1) Her gun 09:05  -> kaynaklari ceker (fetch)
# 2) Her pazartesi 08:45 -> ceker + haftalik ozeti uretir (weekly)
# Bilgisayar o saatte kapaliysa, acildiginda ilk firsatta calisir (StartWhenAvailable).

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw  = Join-Path $root ".venv\Scripts\pythonw.exe"
$run  = Join-Path $root "run.py"

if (-not (Test-Path $pyw)) {
    Write-Host "[HATA] Sanal ortam bulunamadi. Once kurulum.bat calistirin." -ForegroundColor Red
    exit 1
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

$fetchAction  = New-ScheduledTaskAction -Execute $pyw -Argument "`"$run`" fetch"  -WorkingDirectory $root
$weeklyAction = New-ScheduledTaskAction -Execute $pyw -Argument "`"$run`" weekly" -WorkingDirectory $root

$fetchTrigger  = New-ScheduledTaskTrigger -Daily -At "09:05"
$weeklyTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "08:45"

Register-ScheduledTask -TaskName "QuantIntel - Gunluk Cekme" -Action $fetchAction `
    -Trigger $fetchTrigger -Settings $settings -Force `
    -Description "Quant kaynaklarini ceker ve SQLite arsivine kaydeder." | Out-Null

Register-ScheduledTask -TaskName "QuantIntel - Haftalik Ozet" -Action $weeklyAction `
    -Trigger $weeklyTrigger -Settings $settings -Force `
    -Description "Kaynaklari ceker ve digests klasorune haftalik ozeti yazar." | Out-Null

Write-Host "Gorevler kuruldu:" -ForegroundColor Green
Write-Host "  QuantIntel - Gunluk Cekme   : her gun 09:05"
Write-Host "  QuantIntel - Haftalik Ozet  : her pazartesi 08:45"
Write-Host "Gorev Zamanlayici (taskschd.msc) icinden saatleri degistirebilirsiniz."

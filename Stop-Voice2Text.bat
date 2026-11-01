@echo off
setlocal
set "VOICE2TEXT_STOP_DIR=%~dp0"
echo Oprim instantele Voice2Text active...
powershell -NoProfile -Command "$scriptPath = Join-Path $env:VOICE2TEXT_STOP_DIR 'Voice2Text.pyw'; $scriptPattern = '(?:^|\s|\x22)' + [regex]::Escape($scriptPath) + '(?=\s|\x22|$)'; $exePath = Join-Path $env:VOICE2TEXT_STOP_DIR 'Voice2Text.exe'; Get-CimInstance Win32_Process | Where-Object { ($_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -and $_.CommandLine -match $scriptPattern) -or ($_.Name -eq 'Voice2Text.exe' -and $_.ExecutablePath -eq $exePath) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction Continue }"
echo Gata.
pause

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$executable = Join-Path $projectRoot 'Voice2Text.exe'
$icon = Join-Path $projectRoot 'icon.ico'
if (-not (Test-Path -LiteralPath $executable)) { throw 'Run Build-Portable-EXE.bat first.' }
if (-not (Test-Path -LiteralPath $icon)) { throw 'Voice2Text icon.ico is missing.' }
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'Voice2Text.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $executable
$shortcut.WorkingDirectory = $projectRoot
$shortcut.IconLocation = $icon + ',0'
$shortcut.Description = 'Voice2Text - Dictare vocala offline (F9)'
$shortcut.WindowStyle = 1
$shortcut.Save()
Write-Output ('Shortcut created: ' + $shortcutPath)

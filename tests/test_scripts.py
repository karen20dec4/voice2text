import json
import os
from pathlib import Path
import subprocess
import unittest


class LauncherTests(unittest.TestCase):
    def test_stop_script_only_targets_this_application(self):
        root = Path(__file__).resolve().parents[1]
        line = next(line for line in (root / "Stop-Voice2Text.bat").read_text().splitlines()
                    if line.startswith("powershell "))
        command = line.split('-Command "', 1)[1][:-1]
        fixtures = r'''
$script:stopped = @()
function Get-CimInstance {
    $target = Join-Path $env:VOICE2TEXT_STOP_DIR 'Voice2Text.pyw'
    @(
        [pscustomobject]@{Name='pythonw.exe'; ProcessId=1; CommandLine=('pythonw.exe "' + $target + '"'); ExecutablePath=''},
        [pscustomobject]@{Name='powershell.exe'; ProcessId=2; CommandLine=('powershell matching ' + $target); ExecutablePath=''},
        [pscustomobject]@{Name='python.exe'; ProcessId=3; CommandLine='python.exe "C:\Other\Voice2Text.pyw"'; ExecutablePath=''},
        [pscustomobject]@{Name='Voice2Text.exe'; ProcessId=4; CommandLine=''; ExecutablePath=(Join-Path $env:VOICE2TEXT_STOP_DIR 'Voice2Text.exe')},
        [pscustomobject]@{Name='Voice2Text.exe'; ProcessId=5; CommandLine=''; ExecutablePath='C:\Other\Voice2Text.exe'},
        [pscustomobject]@{Name='python.exe'; ProcessId=6; CommandLine=('python.exe "' + $target + '.backup"'); ExecutablePath=''}
    )
}
function Stop-Process {
    param([int]$Id, [switch]$Force, [string]$ErrorAction)
    $script:stopped += $Id
}
'''
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                 fixtures + "\n" + command + "\nConvertTo-Json -Compress @($script:stopped)"],
                                capture_output=True, text=True,
                                env=dict(os.environ, VOICE2TEXT_STOP_DIR=str(root)), timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [1, 4])

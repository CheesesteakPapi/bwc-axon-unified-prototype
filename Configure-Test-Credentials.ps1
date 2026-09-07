[CmdletBinding()]
param([switch]$Replace)
$ErrorActionPreference = 'Stop'
$BwcRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BwcPython = Join-Path $BwcRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $BwcPython)) { throw 'Run Setup-BWC-Prototype.cmd first.' }
$BwcArgs = @((Join-Path $BwcRoot 'local_test_credentials.py'), '--configure')
if ($Replace) { $BwcArgs += '--replace' }
& $BwcPython @BwcArgs
if ($LASTEXITCODE -ne 0) { throw 'Local test credential configuration did not complete.' }

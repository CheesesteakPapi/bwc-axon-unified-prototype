[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Server = Join-Path $Root 'BWC_Geographic_Operations_v1_0_0\backend_server.py'
if (-not (Test-Path $Python)) { throw 'Run Setup-BWC-Prototype.cmd once before starting the application.' }
Write-Host 'Starting BWC Geographic Operations V3.2.0...'
Write-Host 'The launcher selects an available loopback port and opens a tokenized local URL.'
& $Python $Server --open --auto-port
if ($LASTEXITCODE -ne 0) { throw "Geographic Operations stopped with exit code $LASTEXITCODE." }

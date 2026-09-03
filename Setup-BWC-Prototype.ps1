[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root '.venv'

Write-Host 'BWC Axon Unified Prototype V3.1.0 setup'
Write-Host 'Prototype - Python/PowerShell source execution'
Write-Host 'Not a signed production desktop release'

if (Test-Path (Join-Path $Venv 'Scripts\python.exe')) {
    Write-Host "Existing per-user environment found: $Venv"
} else {
    $PythonCommand = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        & $PythonCommand.Source -3 -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11 or newer is required.'"
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
        & $PythonCommand.Source -3 -m venv $Venv
    } else {
        $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $PythonCommand) { throw 'Install an approved Python 3.11 or newer per-user runtime, then run setup again.' }
        & $PythonCommand.Source -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11 or newer is required.'"
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
        & $PythonCommand.Source -m venv $Venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'The per-user Python environment could not be created.' }
}

$Python = Join-Path $Venv 'Scripts\python.exe'
& $Python -m pip install --disable-pip-version-check --require-hashes -r (Join-Path $Root 'requirements.lock')
if ($LASTEXITCODE -ne 0) { throw 'Runtime dependency verification failed.' }

& $Python -m py_compile `
    (Join-Path $Root 'shared_workspace.py') `
    (Join-Path $Root 'provisioning_workflow.py') `
    (Join-Path $Root 'Axon_BWC_Provisioning_Center_v1_0_0\backend_server.py') `
    (Join-Path $Root 'BWC_Geographic_Operations_v1_0_0\backend_server.py')
if ($LASTEXITCODE -ne 0) { throw 'Python source validation failed.' }

Write-Host ''
Write-Host 'Setup completed without administrative privileges.'
Write-Host 'Start Provisioning Center: Start-Provisioning-Prototype.cmd'
Write-Host 'Start Geographic Operations: Start-Geographic-Prototype.cmd'

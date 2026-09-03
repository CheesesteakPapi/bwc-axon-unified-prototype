@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Provisioning-Prototype.ps1"
if errorlevel 1 pause

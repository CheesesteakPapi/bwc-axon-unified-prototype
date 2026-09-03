@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Geographic-Prototype.ps1"
if errorlevel 1 pause

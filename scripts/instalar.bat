@echo off
REM Instalador do OrganizaLocal para Windows: libera a execucao do script PowerShell so para esta chamada.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" %*
if errorlevel 1 pause

@echo off
REM Desinstalador do OrganizaLocal para Windows.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0desinstalar.ps1" %*
pause

@echo off
REM Executa o OrganizaLocal direto do repositorio, sem instalar (modo desenvolvimento).
REM Uso: iniciar.bat            (servico + navegador)
REM      iniciar.bat status     (qualquer comando do CLI)
set "PYTHONPATH=%~dp0..\src"
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
if "%~1"=="" (%PY% -m organizalocal serve) else (%PY% -m organizalocal %*)
if errorlevel 1 pause

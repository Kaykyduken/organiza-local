# =============================================================================
# OrganizaLocal - instalador para Windows (PowerShell)
#
# Passos (conceitos de SO):
#   1. Localiza o Python 3.10+ (py launcher ou python no PATH)
#   2. Cria a pasta do aplicativo em %APPDATA%\OrganizaLocal  (variavel de ambiente)
#   3. Copia o programa para %APPDATA%\OrganizaLocal\app
#   4. Cria o comando organizalocal.cmd e adiciona a pasta ao PATH do usuario
#   5. Cria atalhos na Area de Trabalho e no Menu Iniciar (abrem o site)
#   6. Coloca o servico na pasta Inicializar (inicia junto com o Windows)
#   7. Inicia o servico em segundo plano e abre o site
#
# Uso (pelo instalar.bat, que libera a execucao do script):
#   instalar.bat [-Site https://seu-site.vercel.app] [-SemAutostart] [-NaoAbrir]
# Nao precisa ser administrador.
# =============================================================================
param(
    [string]$Site = "",
    [switch]$SemAutostart,
    [switch]$NaoAbrir
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot

function Find-Python {
    # O "py launcher" e o jeito oficial de achar o Python no Windows.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $p = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $p) { return $p.Trim() }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $p = & python -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $p -and $p -notmatch "WindowsApps") { return $p.Trim() }
    }
    return $null
}

Write-Host "==> [1/7] Procurando o Python..."
$Py = Find-Python
if (-not $Py) {
    Write-Host "ERRO: Python 3.10+ nao encontrado. Instale em https://www.python.org/downloads/ (marque 'Add python.exe to PATH')." -ForegroundColor Red
    exit 1
}
& $Py -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: e necessario Python 3.10 ou superior." -ForegroundColor Red
    exit 1
}
$PyW = Join-Path (Split-Path $Py) "pythonw.exe"      # versao sem janela de console
if (-not (Test-Path $PyW)) { $PyW = $Py }
Write-Host "    $(& $Py --version) em $Py"

Write-Host "==> [2/7] Criando a pasta do aplicativo..."
$Data = Join-Path $env:APPDATA "OrganizaLocal"
$App = Join-Path $Data "app"
New-Item -ItemType Directory -Force -Path $App, (Join-Path $Data "logs") | Out-Null
Write-Host "    $Data"

Write-Host "==> [3/7] Copiando o programa..."
Remove-Item (Join-Path $App "organizalocal"), (Join-Path $App "web") -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $Repo "src\organizalocal") (Join-Path $App "organizalocal") -Recurse
Copy-Item (Join-Path $Repo "web") (Join-Path $App "web") -Recurse
Get-ChildItem $App -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Write-Host "    $((Get-ChildItem $App -Recurse -File).Count) arquivos copiados."

Write-Host "==> [4/7] Criando o comando 'organizalocal'..."
$Cmd = Join-Path $App "organizalocal.cmd"
Set-Content -Path $Cmd -Encoding ASCII -Value "@echo off`r`ncd /d `"%~dp0`" && `"$Py`" -m organizalocal %*"
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $UserPath) { $UserPath = "" }
if ($UserPath -notlike "*$App*") {
    [Environment]::SetEnvironmentVariable("Path", ($UserPath.TrimEnd(";") + ";" + $App).TrimStart(";"), "User")
    Write-Host "    Pasta adicionada ao PATH do usuario (abra um novo terminal para usar 'organizalocal')."
}

Write-Host "==> [5/7] Criando atalhos..."
$Shell = New-Object -ComObject WScript.Shell
function New-Shortcut([string]$Path, [string]$Arguments, [string]$Description) {
    $s = $Shell.CreateShortcut($Path)
    $s.TargetPath = $PyW
    $s.Arguments = $Arguments
    $s.WorkingDirectory = $App
    $s.IconLocation = "$env:SystemRoot\System32\shell32.dll,3"
    $s.Description = $Description
    $s.Save()
}
$Desktop = [Environment]::GetFolderPath("Desktop")           # funciona com Area de Trabalho no OneDrive
$Programs = [Environment]::GetFolderPath("Programs")
New-Shortcut (Join-Path $Desktop "OrganizaLocal.lnk") "-m organizalocal open" "Abrir o OrganizaLocal"
New-Shortcut (Join-Path $Programs "OrganizaLocal.lnk") "-m organizalocal open" "Abrir o OrganizaLocal"
Write-Host "    Area de Trabalho e Menu Iniciar."

Write-Host "==> [6/7] Inicio automatico..."
$StartupLnk = Join-Path ([Environment]::GetFolderPath("Startup")) "OrganizaLocal (servico).lnk"
if ($SemAutostart) {
    Remove-Item $StartupLnk -ErrorAction SilentlyContinue
    Write-Host "    Ignorado (-SemAutostart)."
} else {
    New-Shortcut $StartupLnk "-m organizalocal serve --no-browser" "Servico do OrganizaLocal"
    Write-Host "    Servico adicionado a pasta Inicializar (shell:startup)."
}

Write-Host "==> [7/7] Iniciando..."
if ($Site) {
    Push-Location $App
    & $Py -c "from organizalocal.storage import Store; s = Store(); s.config['site_url'] = '$Site'.rstrip('/'); s.save_config(); print('    Site configurado:', s.config['site_url'])"
    Pop-Location
}
if ($NaoAbrir) {
    Push-Location $App
    & $Py -c "from organizalocal.cli import spawn_background; spawn_background()"
    Pop-Location
} else {
    Start-Process -FilePath $Py -ArgumentList "-m", "organizalocal", "open" -WorkingDirectory $App -NoNewWindow -Wait
}

Write-Host ""
Write-Host "Instalacao concluida!" -ForegroundColor Green
Write-Host "  Pasta do aplicativo: $Data"
Write-Host "  Abra pelo atalho 'OrganizaLocal' da Area de Trabalho."
Write-Host "  Terminal: organizalocal status | organizalocal codigo | organizalocal stop"

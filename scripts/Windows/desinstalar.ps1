# =============================================================================
# OrganizaLocal - desinstalador para Windows
# Encerra o servico, remove atalhos, inicio automatico, PATH e o codigo.
# Regras, historico e backups sao mantidos, exceto com -ApagarDados.
# Uso: desinstalar.bat [-ApagarDados]
# =============================================================================
param([switch]$ApagarDados)
$Data = Join-Path $env:APPDATA "OrganizaLocal"
$App = Join-Path $Data "app"

Write-Host "==> Encerrando o servico..."
$Cmd = Join-Path $App "organizalocal.cmd"
if (Test-Path $Cmd) { & $Cmd stop }

Write-Host "==> Removendo atalhos e inicio automatico..."
Remove-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "OrganizaLocal.lnk") -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath("Programs")) "OrganizaLocal.lnk") -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath("Startup")) "OrganizaLocal (servico).lnk") -ErrorAction SilentlyContinue

Write-Host "==> Removendo do PATH do usuario..."
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath) {
    $novo = ($UserPath.Split(";") | Where-Object { $_ -and $_ -ne $App }) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $novo, "User")
}

Write-Host "==> Removendo o codigo instalado..."
Remove-Item $App -Recurse -Force -ErrorAction SilentlyContinue

if ($ApagarDados) {
    $r = Read-Host "Apagar TAMBEM regras, historico e backups em $Data ? [s/N]"
    if ($r -eq "s" -or $r -eq "S") { Remove-Item $Data -Recurse -Force; Write-Host "    Dados apagados." }
} else {
    Write-Host "    Dados mantidos em $Data (use -ApagarDados para remover)."
}
Write-Host "Desinstalacao concluida."

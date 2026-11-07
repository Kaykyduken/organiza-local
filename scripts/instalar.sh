#!/usr/bin/env bash
# =============================================================================
# OrganizaLocal — instalador para Linux
#
# O que este script faz (conceitos de SO em cada passo):
#   1. Verifica se o Python 3.10+ está instalado          -> comandos do sistema
#   2. Cria a pasta do aplicativo ~/.local/share/OrganizaLocal com permissão 700
#                                                          -> diretórios e permissões
#   3. Copia o código para <pasta>/app                     -> manipulação de arquivos
#   4. Cria o comando `organizalocal` em ~/.local/bin      -> PATH / variáveis de ambiente
#   5. Cria atalho no menu de aplicativos e na Área de Trabalho (.desktop)
#   6. Agenda o serviço para iniciar no boot com o cron (@reboot)
#                                                          -> agendamento de tarefas
#   7. Inicia o serviço em segundo plano e abre o site     -> processos
#
# Uso:  ./scripts/instalar.sh [--site https://seu-site.vercel.app] [--sem-autostart] [--nao-abrir]
# =============================================================================
set -euo pipefail

SITE_URL=""
AUTOSTART=1
ABRIR=1
while [ $# -gt 0 ]; do
  case "$1" in
    --site) SITE_URL="${2:-}"; shift 2 ;;
    --sem-autostart) AUTOSTART=0; shift ;;
    --nao-abrir) ABRIR=0; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Opção desconhecida: $1"; exit 1 ;;
  esac
done

# Pasta onde está este script -> raiz do repositório
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/OrganizaLocal"
APP_DIR="$DATA_DIR/app"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/organizalocal"

echo "==> [1/7] Verificando o Python..."
PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
  echo "ERRO: python3 não encontrado. Instale com: sudo apt install python3"
  exit 1
fi
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "ERRO: é necessário Python 3.10 ou superior (encontrado: $("$PYTHON" --version))."
  exit 1
fi
echo "    $("$PYTHON" --version) em $PYTHON"

echo "==> [2/7] Criando a pasta do aplicativo em $DATA_DIR"
mkdir -p "$APP_DIR"
chmod 700 "$DATA_DIR"                       # rwx------ : só o usuário dono acessa

echo "==> [3/7] Copiando o programa..."
rm -rf "$APP_DIR/organizalocal" "$APP_DIR/web"
cp -r "$REPO_DIR/src/organizalocal" "$APP_DIR/organizalocal"
cp -r "$REPO_DIR/web" "$APP_DIR/web"
cp "$REPO_DIR/scripts/verificar_sistema.sh" "$REPO_DIR/scripts/backup_agora.sh" "$APP_DIR/" 2>/dev/null || true
find "$APP_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} +
echo "    $(find "$APP_DIR" -type f | wc -l) arquivos copiados."

echo "==> [4/7] Criando o comando 'organizalocal' em $BIN_DIR"
mkdir -p "$BIN_DIR"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env sh
# Gerado pelo instalador do OrganizaLocal
cd "$APP_DIR" && exec "$PYTHON" -m organizalocal "\$@"
EOF
chmod 755 "$LAUNCHER"                        # rwxr-xr-x : executável
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "    Aviso: $BIN_DIR não está no PATH. Adicione ao ~/.bashrc:  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

echo "==> [5/7] Criando atalhos..."
DESKTOP_FILE="$HOME/.local/share/applications/organizalocal.desktop"
mkdir -p "$(dirname "$DESKTOP_FILE")"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=OrganizaLocal
Comment=Organiza seus downloads e faz backups versionados
Exec=$LAUNCHER open
Icon=folder
Terminal=false
Categories=Utility;FileTools;
EOF
chmod 755 "$DESKTOP_FILE"
DESKTOP_DIR="$(command -v xdg-user-dir >/dev/null && xdg-user-dir DESKTOP || echo "$HOME/Desktop")"
if [ -d "$DESKTOP_DIR" ]; then
  cp "$DESKTOP_FILE" "$DESKTOP_DIR/OrganizaLocal.desktop"
  chmod 755 "$DESKTOP_DIR/OrganizaLocal.desktop"
  command -v gio >/dev/null && gio set "$DESKTOP_DIR/OrganizaLocal.desktop" metadata::trusted true 2>/dev/null || true
  echo "    Atalho criado na Área de Trabalho."
fi

echo "==> [6/7] Início automático do serviço..."
if [ "$AUTOSTART" = "1" ]; then
  if command -v crontab >/dev/null; then
    # Remove linha antiga (se houver) e adiciona a nova: o cron executa no boot.
    ( crontab -l 2>/dev/null | grep -v 'organizalocal serve' || true
      echo "@reboot sleep 20 && $LAUNCHER serve --no-browser >> $DATA_DIR/logs/servico.log 2>&1 # organizalocal serve" ) | crontab -
    echo "    Agendado no cron (@reboot). Veja com: crontab -l"
  else
    mkdir -p "$HOME/.config/autostart"
    sed "s|Exec=.*|Exec=$LAUNCHER serve --no-browser|; s|Name=.*|Name=OrganizaLocal (serviço)|" \
      "$DESKTOP_FILE" > "$HOME/.config/autostart/organizalocal-servico.desktop"
    echo "    cron não encontrado; usando ~/.config/autostart (inicia ao fazer login)."
  fi
else
  echo "    Ignorado (--sem-autostart)."
fi

echo "==> [7/7] Iniciando..."
mkdir -p "$DATA_DIR/logs"
if [ -n "$SITE_URL" ]; then
  # Grava a URL do site da Vercel na configuração (o atalho passa a abrir o site).
  ( cd "$APP_DIR" && "$PYTHON" -c "
from organizalocal.storage import Store
s = Store(); s.config['site_url'] = '$SITE_URL'.rstrip('/'); s.save_config()
print('    Site configurado:', s.config['site_url'])" )
fi
if [ "$ABRIR" = "1" ]; then
  "$LAUNCHER" open || true
else
  ( cd "$APP_DIR" && "$PYTHON" -c "from organizalocal.cli import spawn_background; spawn_background()" )
  sleep 2
  "$LAUNCHER" status || true
fi

echo
echo "Instalação concluída!"
echo "  Pasta do aplicativo: $DATA_DIR"
echo "  Abrir o painel:      organizalocal open"
echo "  Ver situação:        organizalocal status"
echo "  Desinstalar:         $REPO_DIR/scripts/desinstalar.sh"

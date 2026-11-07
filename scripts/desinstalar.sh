#!/usr/bin/env bash
# =============================================================================
# OrganizaLocal — desinstalador para Linux
# Encerra o serviço (sinal SIGTERM), remove o agendamento do cron, os atalhos e o
# código. Suas regras, histórico e backups são MANTIDOS, a não ser que use
# --apagar-dados.
#
# Uso:  ./scripts/desinstalar.sh [--apagar-dados]
# =============================================================================
set -uo pipefail

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/OrganizaLocal"
LAUNCHER="$HOME/.local/bin/organizalocal"
APAGAR_DADOS=0
[ "${1:-}" = "--apagar-dados" ] && APAGAR_DADOS=1

echo "==> Encerrando o serviço..."
if [ -x "$LAUNCHER" ]; then
  "$LAUNCHER" stop || true
elif [ -f "$DATA_DIR/state/server.pid" ]; then
  kill -TERM "$(cat "$DATA_DIR/state/server.pid")" 2>/dev/null || true
fi

echo "==> Removendo o início automático..."
if command -v crontab >/dev/null; then
  crontab -l 2>/dev/null | grep -v 'organizalocal' | crontab - 2>/dev/null || true
fi
rm -f "$HOME/.config/autostart/organizalocal-servico.desktop"

echo "==> Removendo atalhos e comando..."
rm -f "$LAUNCHER" "$HOME/.local/share/applications/organizalocal.desktop"
DESKTOP_DIR="$(command -v xdg-user-dir >/dev/null && xdg-user-dir DESKTOP || echo "$HOME/Desktop")"
rm -f "$DESKTOP_DIR/OrganizaLocal.desktop"

echo "==> Removendo o código instalado..."
rm -rf "$DATA_DIR/app"

if [ "$APAGAR_DADOS" = "1" ]; then
  read -r -p "Apagar TAMBÉM regras, histórico e backups em $DATA_DIR? [s/N] " resposta
  if [ "$resposta" = "s" ] || [ "$resposta" = "S" ]; then
    rm -rf "$DATA_DIR"
    echo "    Dados apagados."
  fi
else
  echo "    Dados mantidos em $DATA_DIR (use --apagar-dados para remover)."
fi
echo "Desinstalação concluída."

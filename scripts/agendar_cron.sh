#!/usr/bin/env bash
# =============================================================================
# OrganizaLocal — agendamento alternativo pelo cron do Linux
#
# O serviço já organiza de hora em hora sozinho enquanto está aberto. Este script
# mostra a ALTERNATIVA clássica do Linux: deixar o cron rodar os comandos de
# terminal, mesmo sem o serviço aberto.
#
#   0 * * * *   organizalocal organize     -> minuto 0 de toda hora
#   30 2 * * *  backup_agora.sh            -> todo dia às 02:30
#
# Uso:  ./scripts/agendar_cron.sh            # instala as entradas
#       ./scripts/agendar_cron.sh --remover  # remove as entradas
#       ./scripts/agendar_cron.sh --listar   # mostra o crontab atual
# =============================================================================
set -euo pipefail

if ! command -v crontab >/dev/null; then
  echo "crontab não encontrado (instale o pacote cron)."
  exit 1
fi
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/OrganizaLocal"
LAUNCHER="$(command -v organizalocal || echo "$HOME/.local/bin/organizalocal")"
MARK="# organizalocal-cron"

case "${1:-}" in
  --remover)
    crontab -l 2>/dev/null | grep -v "$MARK" | crontab -
    echo "Entradas do OrganizaLocal removidas do cron."
    ;;
  --listar)
    crontab -l 2>/dev/null || echo "(crontab vazio)"
    ;;
  *)
    mkdir -p "$DATA_DIR/logs"
    ( crontab -l 2>/dev/null | grep -v "$MARK" || true
      echo "0 * * * * $LAUNCHER organize >> $DATA_DIR/logs/cron.log 2>&1 $MARK"
      echo "30 2 * * * $REPO_DIR/scripts/backup_agora.sh >> $DATA_DIR/logs/cron.log 2>&1 $MARK"
    ) | crontab -
    echo "Agendado! Entradas atuais:"
    crontab -l | grep "$MARK"
    ;;
esac

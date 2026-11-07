#!/usr/bin/env bash
# =============================================================================
# OrganizaLocal — verificação do sistema e do serviço (relatório em texto)
#
# Usa comandos clássicos do Linux para mostrar:
#   uname / uptime          -> sistema e tempo ligado
#   nproc / loadavg          -> CPU
#   free                     -> memória
#   df / du                  -> espaço em disco e tamanho das pastas
#   ps / pgrep               -> processo do serviço
#   ls -ld / stat            -> permissões
#   crontab -l               -> agendamento
#   curl                     -> API local respondendo
# O relatório é exibido e salvo em <pasta de dados>/reports/verificacao_<data>.txt
#
# Uso:  ./scripts/verificar_sistema.sh [pasta_extra ...]
# =============================================================================
set -uo pipefail

DATA_DIR="${ORGANIZALOCAL_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/OrganizaLocal}"
PORT="${ORGANIZALOCAL_PORT:-8765}"
DOWNLOADS="$(command -v xdg-user-dir >/dev/null && xdg-user-dir DOWNLOAD || echo "$HOME/Downloads")"
mkdir -p "$DATA_DIR/reports"
REPORT="$DATA_DIR/reports/verificacao_$(date +%Y%m%d_%H%M%S).txt"

secao() { printf '\n===== %s =====\n' "$1"; }

{
  echo "OrganizaLocal — verificação do sistema em $(date '+%d/%m/%Y %H:%M:%S')"

  secao "Sistema operacional"
  uname -a
  [ -r /etc/os-release ] && grep -E '^PRETTY_NAME=' /etc/os-release | cut -d= -f2 | tr -d '"'
  echo "Ligado há: $(uptime -p 2>/dev/null || uptime)"
  echo "Usuário: $(id -un) (UID $(id -u))"

  secao "CPU"
  echo "Núcleos: $(nproc)"
  [ -r /proc/loadavg ] && echo "Carga média (1/5/15 min): $(cut -d' ' -f1-3 /proc/loadavg)"

  secao "Memória"
  free -h 2>/dev/null || grep -E 'MemTotal|MemAvailable' /proc/meminfo

  secao "Espaço em disco"
  df -h "$HOME" "$DOWNLOADS" "$DATA_DIR" "$@" 2>/dev/null | awk 'NR==1 || !seen[$0]++'

  secao "Tamanho das pastas"
  du -sh "$DOWNLOADS" 2>/dev/null
  du -sh "$DATA_DIR" "$DATA_DIR/backups" "$DATA_DIR/history" 2>/dev/null
  echo "Arquivos soltos em Downloads: $(find "$DOWNLOADS" -maxdepth 1 -type f 2>/dev/null | wc -l)"

  secao "Processo do serviço"
  if pgrep -f 'organizalocal serve' >/dev/null; then
    ps -o pid,ppid,user,%cpu,%mem,rss,etime,cmd -p "$(pgrep -f 'organizalocal serve' | head -n1)"
  else
    echo "Serviço NÃO está em execução (inicie com: organizalocal open)"
  fi
  [ -f "$DATA_DIR/state/server.pid" ] && echo "Arquivo de PID: $(cat "$DATA_DIR/state/server.pid")"

  secao "API local"
  if command -v curl >/dev/null; then
    curl -s --max-time 2 "http://127.0.0.1:$PORT/api/ping" || echo "Sem resposta em 127.0.0.1:$PORT"
    echo
  fi

  secao "Permissões"
  ls -ld "$DATA_DIR" "$DATA_DIR/state" 2>/dev/null
  ls -l "$DATA_DIR/state/session.json" 2>/dev/null || echo "session.json ausente (serviço parado)"

  secao "Agendamento (cron)"
  crontab -l 2>/dev/null | grep organizalocal || echo "Nenhuma entrada do OrganizaLocal no cron."

  secao "Últimas operações registradas"
  if [ -f "$DATA_DIR/history/events.jsonl" ]; then
    tail -n 8 "$DATA_DIR/history/events.jsonl" | sed -E 's/.*"timestamp": "([^"]+)".*"operation": "([^"]+)".*"status": "([^"]+)".*/\1  \2  [\3]/'
    echo "Total de eventos: $(wc -l < "$DATA_DIR/history/events.jsonl")"
  else
    echo "Histórico vazio."
  fi
} 2>&1 | tee "$REPORT"

echo
echo "Relatório salvo em: $REPORT"

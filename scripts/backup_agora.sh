#!/usr/bin/env bash
# =============================================================================
# OrganizaLocal — executa as regras de backup pelo terminal (útil no cron)
#
# Se o serviço estiver aberto, o pedido vai pela API; senão o backup roda direto.
# Código de saída: 0 = sucesso, 1 = alguma regra falhou.
#
# Uso:  ./scripts/backup_agora.sh            # todas as regras de backup
#       ./scripts/backup_agora.sh "Faculdade"  # só a regra com esse nome (ou id)
# =============================================================================
set -uo pipefail

if command -v organizalocal >/dev/null; then
  CMD=(organizalocal)
else
  # Executando direto do repositório (sem instalar)
  REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  export PYTHONPATH="$REPO_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
  CMD=(python3 -m organizalocal)
fi

echo "[$(date '+%F %T')] Iniciando backup ${1:+da regra '$1'}"
if [ -n "${1:-}" ]; then
  "${CMD[@]}" backup --job "$1"
else
  "${CMD[@]}" backup
fi
STATUS=$?
echo "[$(date '+%F %T')] Backup finalizado com código $STATUS"
exit $STATUS

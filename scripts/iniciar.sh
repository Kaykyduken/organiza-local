#!/usr/bin/env bash
# =============================================================================
# OrganizaLocal — executa direto do repositório, SEM instalar (modo desenvolvimento)
# Uso:  ./scripts/iniciar.sh            # serviço em primeiro plano + abre o navegador
#       ./scripts/iniciar.sh status     # qualquer comando do CLI
# =============================================================================
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$REPO_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
if [ $# -eq 0 ]; then
  exec python3 -m organizalocal serve
fi
exec python3 -m organizalocal "$@"

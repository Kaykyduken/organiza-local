#!/usr/bin/env bash
# =============================================================================
# Gera dist/OrganizaLocal-Setup-<versão>.exe
#
# Requisitos: makensis (Linux: sudo apt install nsis | Windows: nsis.sourceforge.io)
#             unzip, e o Python embutido oficial para Windows:
#             python-3.12.10-embed-amd64.zip (baixado automaticamente de python.org,
#             ou coloque-o em installer/windows/ antes de rodar).
# Uso:  ./installer/windows/build.sh
# =============================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
REPO="$(cd ../.. && pwd)"
VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$REPO/src/organizalocal/__init__.py")"
PY_VER="3.12.10"
PY_ZIP="python-$PY_VER-embed-amd64.zip"
PY_SHA256="4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"

echo "==> OrganizaLocal $VERSION — instalador Windows"
if [ ! -f "$PY_ZIP" ]; then
  echo "==> Baixando $PY_ZIP de python.org"
  curl -fL -o "$PY_ZIP" "https://www.python.org/ftp/python/$PY_VER/$PY_ZIP"
fi
echo "$PY_SHA256  $PY_ZIP" | sha256sum -c -        # confere a integridade do Python

rm -rf build && mkdir -p build/python build/app "$REPO/dist"
unzip -q "$PY_ZIP" -d build/python
# O arquivo ._pth define o sys.path do Python embutido: acrescentamos a pasta do app.
printf 'python312.zip\n.\n..\\app\n' > build/python/python312._pth
cp -r "$REPO/src/organizalocal" build/app/organizalocal
cp -r "$REPO/web" build/app/web
rm -rf build/app/web/downloads                      # não embute os próprios instaladores
find build -name '__pycache__' -type d -prune -exec rm -rf {} +

makensis -V2 -DVERSION="$VERSION" organizalocal.nsi
ls -lh "$REPO/dist/OrganizaLocal-Setup-$VERSION.exe"
sha256sum "$REPO/dist/OrganizaLocal-Setup-$VERSION.exe"

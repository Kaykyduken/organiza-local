#!/usr/bin/env bash
# =============================================================================
# Gera dist/organizalocal_<versão>_all.deb (Ubuntu, Debian, Mint, Pop!_OS...)
#
# O pacote instala:
#   /opt/organizalocal/                     código Python + interface web
#   /usr/bin/organizalocal                  comando de terminal
#   /usr/share/applications/organizalocal.desktop      atalho no menu
#   /etc/xdg/autostart/organizalocal-servico.desktop   inicia o serviço no login
#   /usr/share/icons/hicolor/256x256/apps/organizalocal.png
# Os dados de cada usuário continuam em ~/.local/share/OrganizaLocal.
#
# Instalar:  dois cliques no .deb  ou  sudo apt install ./organizalocal_1.0.0_all.deb
# Remover:   sudo apt remove organizalocal   (os dados do usuário são mantidos)
# =============================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
REPO="$(cd ../.. && pwd)"
VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$REPO/src/organizalocal/__init__.py")"
PKG="organizalocal_${VERSION}_all"
ROOT="build/$PKG"

echo "==> OrganizaLocal $VERSION — pacote .deb"
rm -rf build && mkdir -p "$ROOT/DEBIAN" "$ROOT/opt/organizalocal" "$ROOT/usr/bin" \
  "$ROOT/usr/share/applications" "$ROOT/etc/xdg/autostart" \
  "$ROOT/usr/share/icons/hicolor/256x256/apps" "$ROOT/usr/share/doc/organizalocal" "$REPO/dist"

cp -r "$REPO/src/organizalocal" "$ROOT/opt/organizalocal/"
cp -r "$REPO/web" "$ROOT/opt/organizalocal/"
rm -rf "$ROOT/opt/organizalocal/web/downloads"
cp "$REPO/scripts/verificar_sistema.sh" "$REPO/scripts/backup_agora.sh" "$ROOT/opt/organizalocal/"
find "$ROOT" -name '__pycache__' -type d -prune -exec rm -rf {} +
cp "$REPO/installer/assets/organizalocal.png" "$ROOT/usr/share/icons/hicolor/256x256/apps/organizalocal.png"

# Comando de terminal
cat > "$ROOT/usr/bin/organizalocal" <<'EOF'
#!/bin/sh
# OrganizaLocal — comando instalado pelo pacote .deb
cd /opt/organizalocal && exec python3 -m organizalocal "$@"
EOF

# Atalho no menu de aplicativos
cat > "$ROOT/usr/share/applications/organizalocal.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=OrganizaLocal
GenericName=Organizador de arquivos
Comment=Organiza seus downloads e faz backups versionados
Exec=organizalocal open
Icon=organizalocal
Terminal=false
Categories=Utility;FileTools;
Keywords=organizar;downloads;backup;arquivos;
EOF

# Início automático do serviço ao entrar na sessão (cada usuário pode desativar
# nas configurações de "Aplicativos de inicialização" da sua distribuição).
cat > "$ROOT/etc/xdg/autostart/organizalocal-servico.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=OrganizaLocal (serviço)
Comment=Organização automática de hora em hora e backups
Exec=organizalocal serve --no-browser
Icon=organizalocal
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF

cat > "$ROOT/usr/share/doc/organizalocal/copyright" <<'EOF'
OrganizaLocal — Projeto Integrador de Sistemas Operacionais, FATEC Itapetininga (2026).
Código-fonte: https://github.com/Kaykyduken/organiza-local
EOF

SIZE_KB=$(du -sk "$ROOT" | cut -f1)
cat > "$ROOT/DEBIAN/control" <<EOF
Package: organizalocal
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.10)
Recommends: xdg-utils, cron
Suggests: 7zip | p7zip-full
Installed-Size: $SIZE_KB
Maintainer: Equipe OrganizaLocal <kaykyduken@users.noreply.github.com>
Homepage: https://organiza-local.vercel.app
Description: Organização automática de arquivos e backups versionados
 Organiza de hora em hora os arquivos da pasta Downloads seguindo regras
 do usuário (extensão, nome, categoria, formato real, tamanho, data, com
 prioridade e exceções) e faz backups com várias versões. Tudo roda no
 computador; o painel web conversa só com 127.0.0.1.
EOF

# Pós-instalação: atualiza o cache de atalhos e ícones
cat > "$ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -f /usr/share/icons/hicolor || true
echo "OrganizaLocal instalado. Abra pelo menu de aplicativos ou rode: organizalocal open"
exit 0
EOF
# Antes de remover: encerra os serviços em execução (sinal SIGTERM)
cat > "$ROOT/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "upgrade" ]; then
  pkill -TERM -f "organizalocal serve" 2>/dev/null || true
fi
# remove os caches .pyc gerados pelo Python (não pertencem ao pacote)
find /opt/organizalocal -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
exit 0
EOF

# Permissões: diretórios 755, arquivos 644, executáveis 755
find "$ROOT" -type d -exec chmod 755 {} +
find "$ROOT" -type f -exec chmod 644 {} +
chmod 755 "$ROOT/usr/bin/organizalocal" "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/prerm" \
  "$ROOT/opt/organizalocal/verificar_sistema.sh" "$ROOT/opt/organizalocal/backup_agora.sh"

dpkg-deb --root-owner-group --build "$ROOT" "$REPO/dist/$PKG.deb"
ls -lh "$REPO/dist/$PKG.deb"
sha256sum "$REPO/dist/$PKG.deb"

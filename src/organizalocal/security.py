"""Segurança: sessão do servidor, pareamento, perfis com PIN e senha crítica.

Como o site da Vercel conversa com o programa no PC:
  1. Ao iniciar, o servidor cria um TOKEN aleatório e um CÓDIGO de 6 dígitos e grava
     ambos em state/session.json com permissão 600 (só o dono do arquivo lê).
  2. O atalho do programa (comando `open`) lê o token e abre o site com
     #token=... na URL. O fragmento (#) nunca é enviado ao servidor da Vercel.
  3. Se o site for aberto sem o token, o usuário digita o código de 6 dígitos
     mostrado por `organizalocal codigo` (pareamento) e recebe um token próprio.
  4. Toda chamada à API exige "Authorization: Bearer <token>" e uma origem
     autorizada (127.0.0.1 ou a URL da Vercel configurada).
"""
from __future__ import annotations

import hashlib
import os
import secrets
import time

from .storage import Store, now, password_hash, password_verify

# Permissões que um perfil pode receber.
PERMISSIONS = {
    "read": "Ver painel, regras, histórico e backups",
    "analyze": "Simular, testar regras e usar ferramentas de análise",
    "organize": "Executar a organização (mover arquivos)",
    "rules": "Criar, editar, excluir e priorizar regras",
    "backups": "Criar e executar regras de backup",
    "restore": "Restaurar backups e desfazer movimentações",
    "delete": "Apagar arquivos (duplicados, quarentena, versões)",
    "settings": "Alterar configurações, perfis e segurança",
}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Security:
    def __init__(self, store: Store):
        self.store = store
        self.token = ""
        self.code = ""
        self.code_created = 0.0
        self.paired_hashes: set[str] = set()   # hashes dos tokens válidos nesta execução
        self.failures: list[float] = []

    # ------------------------------------------------------------------
    # Sessão do servidor
    # ------------------------------------------------------------------
    def start_session(self, port: int) -> dict:
        """Gera token + código e grava a sessão com permissão restrita."""
        self.token = secrets.token_urlsafe(32)
        self.code = f"{secrets.randbelow(900000) + 100000}"
        self.code_created = time.monotonic()
        self.paired_hashes = {_hash_token(self.token)}
        session = {"pid": os.getpid(), "port": port, "token": self.token, "code": self.code,
                   "started": now()}
        self.store.write(self.store.session_path, session, private=True)
        return session

    def end_session(self) -> None:
        self.store.session_path.unlink(missing_ok=True)

    def check_token(self, header: str) -> bool:
        if not header.startswith("Bearer "):
            return False
        return _hash_token(header[7:].strip()) in self.paired_hashes

    def pair(self, code: str) -> str:
        """Troca o código de 6 dígitos por um token (limite de tentativas)."""
        moment = time.monotonic()
        self.failures = [t for t in self.failures if moment - t < 300]
        if len(self.failures) >= 5:
            raise PermissionError("Muitas tentativas. Aguarde 5 minutos.")
        if moment - self.code_created > 1800:
            self.code = f"{secrets.randbelow(900000) + 100000}"   # código expira em 30 min
            self.code_created = moment
            session = self.store.read(self.store.session_path, {})
            session["code"] = self.code
            self.store.write(self.store.session_path, session, private=True)
            raise PermissionError("Código expirado. Rode `organizalocal codigo` para ver o novo.")
        if not secrets.compare_digest(str(code).strip(), self.code):
            self.failures.append(moment)
            raise PermissionError("Código incorreto.")
        token = secrets.token_urlsafe(32)
        self.paired_hashes.add(_hash_token(token))
        self.store.event("pair", "ok")
        return token

    def revoke_all(self, port: int) -> dict:
        """Invalida todos os tokens (inclusive do site aberto) e gera uma nova sessão."""
        self.start_session(port)
        self.store.event("pairing_revoke", "ok")
        return {"revoked": True}

    # ------------------------------------------------------------------
    # Perfis e permissões
    # ------------------------------------------------------------------
    @property
    def profiles(self) -> list[dict]:
        return self.store.config["profiles"]

    def active_profile(self) -> dict:
        name = self.store.config.get("active_profile")
        return next((p for p in self.profiles if p["name"] == name), self.profiles[0])

    def allowed(self, permission: str) -> bool:
        perms = self.active_profile().get("permissions", [])
        return "*" in perms or permission in perms

    def save_profile(self, name: str, permissions: list[str], pin: str = "") -> dict:
        name = str(name).strip()[:40]
        if not name:
            raise ValueError("Informe o nome do perfil.")
        perms = ["*"] if "*" in permissions else [p for p in permissions if p in PERMISSIONS]
        with self.store.lock:
            profile = next((p for p in self.profiles if p["name"] == name), None)
            if not profile:
                profile = {"name": name, "permissions": perms, "pin_hash": ""}
                self.profiles.append(profile)
            profile["permissions"] = perms
            if pin:
                if not pin.isdigit() or not 4 <= len(pin) <= 8:
                    raise ValueError("O PIN deve ter de 4 a 8 dígitos.")
                profile["pin_hash"] = password_hash(pin)
            if not any("*" in p["permissions"] or "settings" in p["permissions"] for p in self.profiles):
                raise ValueError("Pelo menos um perfil precisa da permissão de configurações.")
            self.store.save_config()
        self.store.event("profile_save", "ok", detail=name)
        return {"name": name, "permissions": perms, "has_pin": bool(profile["pin_hash"])}

    def delete_profile(self, name: str) -> dict:
        if name == self.store.config.get("active_profile"):
            raise ValueError("Troque de perfil antes de excluir o perfil ativo.")
        with self.store.lock:
            self.store.config["profiles"] = [p for p in self.profiles if p["name"] != name]
            if not self.store.config["profiles"]:
                raise ValueError("Deve existir pelo menos um perfil.")
            self.store.save_config()
        self.store.event("profile_delete", "ok", detail=name)
        return {"deleted": name}

    def switch_profile(self, name: str, pin: str = "") -> dict:
        profile = next((p for p in self.profiles if p["name"] == name), None)
        if not profile:
            raise ValueError("Perfil não encontrado.")
        if profile.get("pin_hash") and not password_verify(str(pin), profile["pin_hash"]):
            raise PermissionError("PIN incorreto.")
        self.store.config["active_profile"] = name
        self.store.save_config(snapshot=False)
        self.store.event("profile_switch", "ok", detail=name)
        return {"active": name}

    # ------------------------------------------------------------------
    # Senha para operações críticas (opcional)
    # ------------------------------------------------------------------
    def set_critical_password(self, new: str, current: str = "") -> dict:
        saved = self.store.config.get("critical_password_hash", "")
        if saved and not password_verify(current, saved):
            raise PermissionError("Senha atual incorreta.")
        if new and len(new) < 6:
            raise ValueError("A senha precisa de pelo menos 6 caracteres.")
        self.store.config["critical_password_hash"] = password_hash(new) if new else ""
        self.store.save_config()
        self.store.event("password_set", "ok", detail="definida" if new else "removida")
        return {"enabled": bool(new)}

    def require_critical(self, payload: dict) -> None:
        """Operações críticas exigem confirmação e, se configurada, a senha."""
        if not payload.get("confirm"):
            raise PermissionError("Esta operação exige confirmação.")
        saved = self.store.config.get("critical_password_hash", "")
        if saved and not password_verify(str(payload.get("password", "")), saved):
            raise PermissionError("Senha de operações críticas incorreta.")

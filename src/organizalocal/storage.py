"""Persistência local: pasta de dados, configuração, histórico e integridade.

Conceitos de SO usados aqui:
  * Variáveis de ambiente (APPDATA, XDG_DATA_HOME, ORGANIZALOCAL_DATA) para
    descobrir onde gravar os dados de cada usuário em cada sistema.
  * Criação de diretórios e permissões (chmod 700 na pasta de dados no Linux).
  * Escrita atômica: grava em arquivo temporário, força o disco (fsync) e
    troca com os.replace() — se a energia cair no meio, o arquivo antigo
    continua íntegro.
  * Registro de informações operacionais em um log append-only (JSONL).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import secrets
import shutil
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from . import APP_NAME

# Subpastas criadas dentro da pasta de dados do aplicativo.
DATA_FOLDERS = (
    "app",                 # código instalado pelo instalador (scripts/instalar.*)
    "history",             # events.jsonl, review.json, notes.json, storage.json
    "backups",             # versões de backup (quando a regra não define outro destino)
    "protected_versions",  # cópias de segurança feitas antes de substituir arquivos
    "quarantine",          # arquivos suspeitos (nunca são executados)
    "sandboxes",           # áreas isoladas para testar regras com cópias
    "config_versions",     # um snapshot da configuração a cada gravação
    "reports",             # relatórios PDF
    "exports",             # exportações JSON (configuração e simulações)
    "state",               # sessão do servidor (PID, token), snapshots
    "logs",                # saída do serviço quando roda em segundo plano
)


def now() -> str:
    """Data/hora atual em ISO 8601 com fuso horário local (ex.: 2026-11-07T14:30:00-03:00)."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def data_directory() -> Path:
    """Descobre a pasta de dados conforme o sistema operacional.

    Windows: %APPDATA%\\OrganizaLocal          (ex.: C:\\Users\\kayky\\AppData\\Roaming\\OrganizaLocal)
    Linux:   $XDG_DATA_HOME/OrganizaLocal     (padrão ~/.local/share/OrganizaLocal)
    A variável ORGANIZALOCAL_DATA substitui tudo (usada nos testes).
    """
    override = os.environ.get("ORGANIZALOCAL_DATA")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def downloads_directory() -> Path:
    """Pasta Downloads do usuário (padrão monitorado pelo aplicativo).

    No Linux respeita o arquivo ~/.config/user-dirs.dirs (XDG_DOWNLOAD_DIR),
    que muda o nome da pasta em sistemas em português ("Transferências").
    """
    home = Path.home()
    if os.name != "nt":
        user_dirs = home / ".config" / "user-dirs.dirs"
        try:
            for line in user_dirs.read_text(encoding="utf-8").splitlines():
                if line.startswith("XDG_DOWNLOAD_DIR="):
                    value = line.split("=", 1)[1].strip().strip('"')
                    return Path(value.replace("$HOME", str(home)))
        except OSError:
            pass
    return home / "Downloads"


def initial_config() -> dict:
    """Configuração padrão criada na primeira execução."""
    downloads = downloads_directory()
    return {
        "version": 2,
        "theme": "claro",                          # claro | escuro | neon
        "site_url": "",                            # URL da interface publicada na Vercel
        "extra_origins": [],                       # outras origens web autorizadas
        # --- Organização automática ---------------------------------------
        "watch_dirs": [str(downloads)],            # padrão: pasta Downloads
        "recursive": False,                        # olhar subpastas das pastas monitoradas?
        "organize_schedule": {                     # padrão: de hora em hora
            "frequency": "interval",               # off | interval | daily | weekly
            "interval_minutes": 60,
            "time": "09:00",
            "weekday": 0,                          # 0 = segunda-feira
        },
        "organize_on_start": False,                # organizar quando o serviço iniciar
        "conflict_policy": "rename",               # rename | review | skip (RNF10)
        "default_destination": "",                 # destino para arquivos sem regra (vazio = ficam)
        "min_file_age_seconds": 30,                # ignora downloads ainda em andamento
        "quarantine_risky": False,                 # executáveis/formatos disfarçados -> quarentena (opcional)
        "rename_pattern": "",                      # modelo global de nome ({name}, {date}...)
        # --- Regras e listas auxiliares --------------------------------------
        "rules": [],
        "categories": {},                          # categorias personalizadas {nome: [extensões]}
        "projects": [],                            # [{id, name, directory}]
        "protected_paths": [],                     # nunca mexer nestes arquivos/pastas
        "exclusions": {"paths": [], "names": [], "extensions": []},
        "limits": [],                              # [{path|category, max_bytes}]
        "due_dates": [],                           # [{id, file, description, due}]
        # --- Backups -----------------------------------------------------
        "backup_jobs": [],
        "default_max_versions": 5,
        # --- Segurança ---------------------------------------------------
        "profiles": [{"name": "Administrador", "permissions": ["*"], "pin_hash": ""}],
        "active_profile": "Administrador",
        "critical_password_hash": "",
        # --- Estado das execuções ---------------------------------------
        "last_runs": {},
        "first_run": True,
    }


def sha256(path, chunk_size: int = 1024 * 1024) -> str:
    """Calcula o SHA-256 lendo o arquivo em blocos de 1 MiB (pouca memória)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def password_hash(password: str, salt: bytes | None = None) -> str:
    """Gera hash scrypt com sal aleatório (senha nunca é salva em texto puro)."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return salt.hex() + ":" + digest.hex()


def password_verify(password: str, saved: str) -> bool:
    """Confere a senha comparando em tempo constante."""
    if not saved:
        return False
    try:
        salt, digest = saved.split(":", 1)
        candidate = password_hash(password, bytes.fromhex(salt)).split(":", 1)[1]
        return secrets.compare_digest(candidate, digest)
    except (ValueError, TypeError):
        return False


class Store:
    """Centraliza toda leitura/gravação em disco do aplicativo."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root or data_directory()).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        # No Linux, a pasta de dados fica acessível apenas ao dono (rwx------).
        if os.name != "nt":
            try:
                os.chmod(self.root, 0o700)
            except OSError:
                pass
        for folder in DATA_FOLDERS:
            (self.root / folder).mkdir(parents=True, exist_ok=True)

        self.config_path = self.root / "config.json"
        self.history_path = self.root / "history" / "events.jsonl"
        self.review_path = self.root / "history" / "review.json"
        self.notes_path = self.root / "history" / "notes.json"
        self.storage_path = self.root / "history" / "storage.json"
        self.backup_index_path = self.root / "backups" / "index.json"
        self.snapshot_path = self.root / "state" / "snapshots.json"
        self.session_path = self.root / "state" / "session.json"
        self.pid_path = self.root / "state" / "server.pid"
        # RLock: a mesma thread pode adquirir o bloqueio mais de uma vez.
        self.lock = threading.RLock()

        # Carrega a configuração e completa chaves novas (atualizações de versão).
        defaults = initial_config()
        self.config = self.read(self.config_path, defaults)
        self._migrate_v1()                         # antes de completar com os padrões
        for key, value in defaults.items():
            self.config.setdefault(key, copy.deepcopy(value))
        self.save_config(snapshot=False)
        for path, default in ((self.review_path, []), (self.notes_path, []),
                              (self.backup_index_path, {}), (self.storage_path, [])):
            if not path.exists():
                self.write(path, default)

    # ------------------------------------------------------------------
    # Compatibilidade com a configuração da versão 0.9 (pasta OrganizaLocal antiga)
    # ------------------------------------------------------------------
    def _migrate_v1(self) -> None:
        cfg = self.config
        if cfg.get("monitor_dirs") and not cfg.get("watch_dirs"):
            cfg["watch_dirs"] = cfg["monitor_dirs"]
        if cfg.get("backup_sources") and not cfg.get("backup_jobs"):
            cfg["backup_jobs"] = [{
                "id": secrets.token_hex(6), "name": "Backup importado da versão 0.9",
                "sources": cfg["backup_sources"], "destination": "", "mode": "zip",
                "include_extensions": [], "exclude_patterns": [], "interval_hours": 24,
                "max_versions": int(cfg.get("backup_limit", 5)), "skip_unchanged": True,
                "enabled": False,
            }]
        for old_key in ("monitor_dirs", "backup_sources", "backup_limit", "monitor_enabled",
                        "interval_seconds", "watched_snapshots", "backup_schedule"):
            cfg.pop(old_key, None)
        cfg["version"] = 2

    # ------------------------------------------------------------------
    # JSON genérico com escrita atômica
    # ------------------------------------------------------------------
    def read(self, path, default):
        """Lê JSON; se não existir ou estiver corrompido, devolve o padrão."""
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return copy.deepcopy(default)

    def write(self, path, data, private: bool = False) -> None:
        """Grava JSON de forma atômica (temporário + fsync + os.replace)."""
        path = Path(path)
        with self.lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
            try:
                with open(temporary, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, indent=2, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())      # garante que os dados chegaram ao disco
                if private and os.name != "nt":
                    os.chmod(temporary, 0o600)     # rw------- : só o dono lê (token de sessão)
                os.replace(temporary, path)        # troca atômica no sistema de arquivos
            finally:
                if temporary.exists():
                    temporary.unlink()

    # ------------------------------------------------------------------
    # Configuração (RNF08 — persistência) e versões da configuração
    # ------------------------------------------------------------------
    def save_config(self, snapshot: bool = True) -> None:
        """Salva config.json. Com snapshot=True, guarda antes uma cópia datada."""
        with self.lock:
            if snapshot and self.config_path.exists():
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                shutil.copy2(self.config_path, self.root / "config_versions" / f"{stamp}.json")
                versions = sorted((self.root / "config_versions").glob("*.json"))
                for old in versions[:-100]:       # mantém só as 100 versões mais recentes
                    old.unlink(missing_ok=True)
            self.write(self.config_path, self.config)

    def config_versions(self) -> list[dict]:
        folder = self.root / "config_versions"
        files = sorted(folder.glob("*.json"), reverse=True)[:100]
        return [{"filename": f.name, "bytes": f.stat().st_size,
                 "timestamp": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")}
                for f in files]

    def restore_config_version(self, filename: str) -> dict:
        target = (self.root / "config_versions" / filename).resolve()
        if target.parent != (self.root / "config_versions").resolve() or not target.is_file():
            raise ValueError("Versão de configuração não encontrada.")
        data = self.read(target, None)
        if not isinstance(data, dict) or "rules" not in data:
            raise ValueError("Arquivo de versão inválido.")
        with self.lock:
            self.save_config(snapshot=True)        # a configuração atual também vira versão
            defaults = initial_config()
            for key, value in defaults.items():
                data.setdefault(key, value)
            self.config = data
            self.save_config(snapshot=False)
        self.event("config_restore", "ok", reference=filename)
        return {"restored": filename}

    # ------------------------------------------------------------------
    # Histórico de operações (RNF05 do projeto antigo / RF14)
    # ------------------------------------------------------------------
    def event(self, operation: str, status: str, **details) -> dict:
        """Acrescenta uma linha ao events.jsonl. Nunca reescreve linhas antigas."""
        item = {"id": secrets.token_hex(8), "timestamp": now(),
                "operation": operation, "status": status, **details}
        line = json.dumps(item, ensure_ascii=False, default=str)
        with self.lock:
            with open(self.history_path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return item

    def history(self, filters: dict | None = None, limit: int = 500) -> list[dict]:
        """Lê o histórico do mais recente para o mais antigo, com filtros e busca."""
        filters = filters or {}
        if not self.history_path.exists():
            return []
        found: deque = deque(maxlen=max(1, int(limit)))
        query = str(filters.get("q", "")).casefold()
        with self.lock, open(self.history_path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                skip = False
                for key in ("operation", "status", "run_id", "rule_id"):
                    wanted = filters.get(key)
                    if wanted and str(event.get(key, "")).casefold() != str(wanted).casefold():
                        skip = True
                if filters.get("date") and not str(event.get("timestamp", "")).startswith(filters["date"]):
                    skip = True
                if query and query not in json.dumps(event, ensure_ascii=False).casefold():
                    skip = True
                if not skip:
                    found.appendleft(event)
        return list(found)

    def find_event(self, event_id: str) -> dict | None:
        for event in self.history(limit=100000):
            if event.get("id") == event_id:
                return event
        return None

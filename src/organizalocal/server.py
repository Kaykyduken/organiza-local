"""Servidor HTTP local (somente 127.0.0.1) que liga o site da Vercel ao computador.

* Escuta APENAS na interface de loopback (127.0.0.1): nenhum outro computador da rede
  consegue acessar.
* Também serve a pasta web/ em http://127.0.0.1:8765, para uso 100% offline.
* Cabeçalhos CORS + "Access-Control-Allow-Private-Network" permitem que a página
  HTTPS publicada na Vercel chame o programa local (o Chrome pede permissão de
  "rede local" na primeira vez).
* Cada ação exige token (Authorization: Bearer) e uma permissão do perfil ativo.

Usa somente http.server da biblioteca padrão (ThreadingHTTPServer = uma thread por
requisição; o agendador roda em outra thread).
"""
from __future__ import annotations

import copy
import json
import mimetypes
import os
import re
import secrets
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import APP_NAME, DEFAULT_PORT, VERSION
from . import archives, rules as R, sysinfo
from .backups import Backups
from .organizer import ACTION_LABELS, Organizer, friendly_error
from .reports import Reports
from .scheduler import Scheduler
from .security import PERMISSIONS, Security
from .storage import Store, now

MAX_BODY = 2 * 1024 * 1024


def web_directory() -> Path:
    """Pasta web/ tanto no repositório (src/../web) quanto na instalação (app/web)."""
    here = Path(__file__).resolve().parent
    for candidate in (here.parent / "web", here.parent.parent / "web"):
        if (candidate / "index.html").is_file():
            return candidate
    return here.parent.parent / "web"


def origin_of(url: str) -> str:
    parsed = urlparse(url.strip())
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""


class App:
    """Junta todos os módulos e expõe as ações chamadas pela interface."""

    def __init__(self, data_root=None, port: int = DEFAULT_PORT, start_scheduler: bool = True):
        self.port = port
        self.store = Store(data_root)
        self.organizer = Organizer(self.store)
        self.backups = Backups(self.store, self.organizer)
        self.reports = Reports(self.store)
        self.security = Security(self.store)
        self.scheduler = Scheduler(self.store, self.organizer, self.backups, self.reports)
        self._first_run_setup()
        self.start_scheduler = start_scheduler

    def _first_run_setup(self) -> None:
        cfg = self.store.config
        if cfg.get("first_run"):
            if not cfg["rules"]:
                cfg["rules"] = R.example_rules(Path.home())
            # Primeira organização automática acontece 1 intervalo depois da instalação.
            cfg["last_runs"]["organize"] = now()
            cfg["first_run"] = False
            self.store.save_config(snapshot=False)
            self.store.event("install", "ok", detail=f"{APP_NAME} {VERSION} iniciado pela primeira vez")

    # ------------------------------------------------------------------
    # Origens autorizadas (CORS)
    # ------------------------------------------------------------------
    def allowed_origins(self) -> set[str]:
        origins = {f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"}
        for url in [self.store.config.get("site_url", "")] + list(self.store.config.get("extra_origins", [])):
            if origin_of(url):
                origins.add(origin_of(url))
        env = os.environ.get("ORGANIZALOCAL_ALLOWED_ORIGIN", "")
        if origin_of(env):
            origins.add(origin_of(env))
        return origins

    # ------------------------------------------------------------------
    # Estado completo para a interface
    # ------------------------------------------------------------------
    def safe_config(self) -> dict:
        cfg = copy.deepcopy(self.store.config)
        cfg["profiles"] = [{"name": p["name"], "permissions": p["permissions"], "has_pin": bool(p.get("pin_hash"))}
                           for p in cfg.get("profiles", [])]
        cfg["critical_password_enabled"] = bool(cfg.pop("critical_password_hash", ""))
        return cfg

    def state(self) -> dict:
        index = self.backups.index()
        return {
            "app": {"name": APP_NAME, "version": VERSION, "data_dir": str(self.store.root), "port": self.port,
                    "os": os.name, "platform": sysinfo.platform.system()},
            "config": self.safe_config(),
            "rules": self.organizer.ordered_rules(),
            "problems": self.organizer.validate_all(),
            "stats": self.reports.stats(),
            "scheduler": self.scheduler.status(),
            "latest": self.store.history(limit=25),
            "review": self.organizer.review_list(),
            "backup_jobs": [{**j, "folder": str(self.backups.folder_for(j)), "next_run": self.backups.next_run(j),
                             "versions": index.get(j["id"], [])} for j in self.store.config["backup_jobs"]],
            "quarantine": self.organizer.quarantine_list(),
            "alerts": self.reports.check_limits(),
            "due_documents": self.reports.due_documents(),
            "notes": self.store.read(self.store.notes_path, []),
            "categories_builtin": R.CATEGORIES,
            "format_labels": R.FORMAT_LABELS,
            "action_labels": ACTION_LABELS,
            "permissions": PERMISSIONS,
            "active_profile": self.security.active_profile()["name"],
            "allowed_origins": sorted(self.allowed_origins()),
            "timestamp": now(),
        }

    # ------------------------------------------------------------------
    # Configurações gerais
    # ------------------------------------------------------------------
    def update_config(self, changes: dict) -> dict:
        allowed = {"theme", "site_url", "extra_origins", "watch_dirs", "recursive", "organize_schedule",
                   "organize_on_start", "conflict_policy", "default_destination", "min_file_age_seconds",
                   "quarantine_risky", "rename_pattern", "protected_paths", "exclusions", "default_max_versions"}
        if not isinstance(changes, dict) or not set(changes) <= allowed:
            raise ValueError("Configuração não permitida: " + ", ".join(set(changes) - allowed))
        fresh = copy.deepcopy(self.store.config)
        for key, value in changes.items():
            if key in ("watch_dirs", "protected_paths"):
                value = [str(Path(p).expanduser()) for p in value if str(p).strip()]
                if key == "watch_dirs":
                    for p in value:
                        if not Path(p).is_absolute():
                            raise ValueError(f"Use caminho completo: {p}")
                        if self.organizer.protected(p, is_dir=True):
                            raise ValueError("Uma pasta monitorada não pode conter a pasta de dados do aplicativo.")
            elif key == "theme" and value not in ("claro", "escuro", "neon"):
                raise ValueError("Tema inválido.")
            elif key == "conflict_policy" and value not in ("rename", "review", "skip"):
                raise ValueError("Política de conflito inválida.")
            elif key == "organize_schedule":
                if value.get("frequency") not in ("off", "interval", "daily", "weekly"):
                    raise ValueError("Frequência inválida.")
                value["interval_minutes"] = max(1, min(10080, int(value.get("interval_minutes", 60))))
                if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(value.get("time", "09:00"))):
                    raise ValueError("Horário inválido (use HH:MM).")
                value["weekday"] = int(value.get("weekday", 0)) % 7
            elif key == "site_url":
                value = str(value).strip().rstrip("/")
                if value and not origin_of(value).startswith(("https://", "http://")):
                    raise ValueError("URL do site inválida (ex.: https://organiza-local.vercel.app).")
            elif key == "extra_origins":
                value = [origin_of(v) for v in value if origin_of(v)]
            elif key == "exclusions":
                value = {"paths": [str(Path(p).expanduser()) for p in value.get("paths", []) if str(p).strip()],
                         "names": [str(n).strip() for n in value.get("names", []) if str(n).strip()],
                         "extensions": [R.normalize_extension(e) for e in value.get("extensions", []) if str(e).strip()]}
            elif key == "default_destination" and value:
                value = str(Path(value).expanduser())
                if not Path(value).is_absolute() or self.organizer.protected(value, is_dir=True):
                    raise ValueError("Destino padrão inválido ou protegido.")
            elif key in ("recursive", "organize_on_start", "quarantine_risky"):
                value = bool(value)
            elif key == "min_file_age_seconds":
                value = max(0, min(86400, int(value)))
            elif key == "default_max_versions":
                value = max(1, min(100, int(value)))
            fresh[key] = value
        with self.store.lock:
            self.store.config = fresh
            self.store.save_config()
        self.store.event("config_save", "ok", detail=", ".join(changes))
        return self.safe_config()

    def save_list(self, name: str, items: list) -> list:
        """Projetos, limites, vencimentos e categorias personalizadas."""
        if name == "categories":
            if not isinstance(items, dict):
                raise ValueError("Categorias inválidas.")
            value = {str(k).strip(): [R.normalize_extension(e) for e in R._as_list(v)]
                     for k, v in items.items() if str(k).strip()}
        elif name in ("projects", "limits", "due_dates"):
            if not isinstance(items, list):
                raise ValueError("Lista inválida.")
            value = []
            for item in items:
                item = dict(item)
                item.setdefault("id", secrets.token_hex(4))
                if name == "projects" and not Path(str(item.get("directory", ""))).is_absolute():
                    raise ValueError("A pasta do projeto deve ser um caminho completo.")
                if name == "due_dates":
                    datetime.fromisoformat(str(item.get("due")))
                if name == "limits":
                    item["max_bytes"] = int(item.get("max_bytes") or 0)
                value.append(item)
        else:
            raise ValueError("Lista desconhecida.")
        self.store.config[name] = value
        self.store.save_config()
        self.store.event("config_save", "ok", detail=name)
        return value

    def export_config(self) -> dict:
        name = datetime.now().strftime("configuracao_%Y%m%d_%H%M%S.json")
        data = {"format": "organiza-local-2", "exported": now(), "settings": self.safe_config()}
        data["settings"].pop("profiles", None)
        self.store.write(self.store.root / "exports" / name, data)
        return {"filename": name, "data": data}

    def import_config(self, data: dict) -> dict:
        if not isinstance(data, dict) or data.get("format") not in ("organiza-local-1", "organiza-local-2"):
            raise ValueError("Arquivo de exportação incompatível.")
        cfg = data.get("settings") or {}
        rules = [R.normalize_rule(r) for r in cfg.get("rules", [])]
        for rule in rules:
            rule.setdefault("id", secrets.token_hex(6))
        keys = ("theme", "site_url", "watch_dirs", "recursive", "organize_schedule", "conflict_policy",
                "default_destination", "min_file_age_seconds", "quarantine_risky", "rename_pattern",
                "protected_paths", "exclusions", "categories", "projects", "limits", "due_dates", "backup_jobs")
        with self.store.lock:
            self.store.save_config(snapshot=True)
            for key in keys:
                if key in cfg:
                    self.store.config[key] = cfg[key]
            self.store.config["rules"] = rules
            if data["format"] == "organiza-local-1" and "monitor_dirs" in cfg:
                self.store.config["watch_dirs"] = cfg["monitor_dirs"]
            self.store.save_config(snapshot=False)
        self.store.event("config_import", "ok", detail=f"{len(rules)} regras")
        return {"imported": True, "rules": len(rules)}

    def save_note(self, payload: dict) -> dict:
        notes = self.store.read(self.store.notes_path, [])
        note_id = payload.get("id")
        if payload.get("type", "file") not in ("file", "rule", "operation", "backup"):
            raise ValueError("Tipo de observação inválido.")
        item = next((n for n in notes if n["id"] == note_id), None) if note_id else None
        if not item:
            item = {"id": secrets.token_hex(5), "created": now()}
            notes.append(item)
        item.update({"type": payload.get("type", "file"), "ref": str(payload.get("ref", ""))[:500],
                     "text": str(payload.get("text", ""))[:3000], "updated": now()})
        self.store.write(self.store.notes_path, notes)
        return item

    def delete_note(self, note_id: str) -> dict:
        notes = [n for n in self.store.read(self.store.notes_path, []) if n["id"] != note_id]
        self.store.write(self.store.notes_path, notes)
        return {"deleted": note_id}

    # ------------------------------------------------------------------
    # Tabela de ações: nome -> (permissão, função)
    # ------------------------------------------------------------------
    def actions(self) -> dict:
        o, b, rp, s = self.organizer, self.backups, self.reports, self.security
        crit = s.require_critical

        def critical(fn):
            def wrapper(p):
                crit(p)
                return fn(p)
            return wrapper

        def confirmed(fn):
            def wrapper(p):
                if not p.get("confirm"):
                    raise PermissionError("Confirme a operação.")
                return fn(p)
            return wrapper

        return {
            # leitura
            "state": ("read", lambda p: self.state()),
            "history": ("read", lambda p: self.store.history(p.get("filters", {}), int(p.get("limit", 500)))),
            "review_list": ("read", lambda p: o.review_list()),
            "config_versions": ("read", lambda p: self.store.config_versions()),
            "backup_manifest": ("read", lambda p: b.manifest(p["job_id"], p["version_id"])),
            "file_history": ("read", lambda p: b.file_history(p["path"])),
            "storage_history": ("read", lambda p: rp.storage_history()),
            "sandbox_list": ("read", lambda p: o.sandbox_list()),
            "sysinfo": ("read", lambda p: sysinfo.collect(self.store, self.scheduler)),
            "profile_switch": ("read", lambda p: s.switch_profile(p["name"], p.get("pin", ""))),
            # análise / simulação (HU10)
            "simulate": ("analyze", lambda p: o.simulate(p.get("paths") or None, p.get("only_rule") or None)),
            "simulate_export": ("analyze", lambda p: rp.export_simulation(
                o.simulate(p.get("paths") or None, p.get("only_rule") or None))),
            "rules_validate": ("analyze", lambda p: o.validate_all()),
            "duplicates": ("analyze", lambda p: o.duplicates(p.get("paths") or None)),
            "suggestions": ("analyze", lambda p: o.suggestions(p.get("paths") or None)),
            "extensions_scan": ("analyze", lambda p: o.extension_inventory(p.get("paths") or None,
                                                                         p.get("recursive"))),
            "integrity": ("analyze", lambda p: o.integrity(p["path"], p.get("expected", ""))),
            "archive_inspect": ("analyze", lambda p: archives.inspect(o, p["path"])),
            "sandbox_run": ("analyze", lambda p: o.sandbox_run(p.get("paths") or None)),
            "sandbox_delete": ("analyze", lambda p: o.sandbox_delete(p["id"])),
            "storage_snapshot": ("analyze", lambda p: rp.storage_snapshot()),
            "backup_compare": ("analyze", lambda p: b.compare(p["job_id"], p["a"], p["b"])),
            "backup_verify": ("analyze", lambda p: b.verify(p["job_id"], p["version_id"])),
            "report": ("analyze", lambda p: rp.daily_pdf(p.get("day", ""))),
            # organização (HU11)
            "organize": ("organize", lambda p: o.organize(p.get("paths") or None, p.get("only_rule") or None,
                                                          p.get("conflict") or None)),
            "review_decide": ("organize", lambda p: o.resolve_review(p["id"], p["decision"],
                                                                     p.get("destination", ""), bool(p.get("confirm")))),
            "rename_file": ("organize", lambda p: o.rename_file(p["path"], p["pattern"], int(p.get("sequence", 1)))),
            "archive_extract": ("organize", lambda p: archives.extract(o, p["path"], p["directory"])),
            # regras (HU03–HU09)
            "rule_save": ("rules", lambda p: o.save_rule(p["rule"], p.get("id") or None)),
            "rule_delete": ("rules", confirmed(lambda p: o.delete_rule(p["id"]))),
            "rule_duplicate": ("rules", lambda p: o.duplicate_rule(p["id"])),
            "rule_toggle": ("rules", lambda p: o.set_enabled(p["id"], bool(p["enabled"]))),
            "rule_priority": ("rules", lambda p: o.change_priority(p["id"], p.get("delta"), p.get("value"))),
            # backups
            "backup_job_save": ("backups", lambda p: b.save_job(p["job"] | {"confirm": p.get("confirm")},
                                                                 p.get("id") or None)),
            "backup_job_delete": ("backups", confirmed(lambda p: b.delete_job(p["id"], bool(p.get("delete_files"))))),
            "backup_run": ("backups", lambda p: b.run(p["id"])),
            "backup_lock": ("backups", lambda p: b.set_locked(p["job_id"], p["version_id"], bool(p["locked"]))),
            "open_backups": ("backups", lambda p: b.open_folder(p.get("job_id", ""))),
            # restauração
            "backup_restore": ("restore", critical(lambda p: b.restore(p["job_id"], p["version_id"],
                                                                       p.get("target_dir", ""), p.get("only"), True))),
            "undo": ("restore", lambda p: o.undo(p["event_id"])),
            # exclusões de arquivos
            "duplicate_remove": ("delete", critical(lambda p: o.remove_duplicate(p["path"], p["keep"]))),
            "quarantine_action": ("delete", critical(lambda p: o.quarantine_action(p["action"], p["name"],
                                                                                   p.get("destination", ""), True))),
            "backup_delete_version": ("delete", critical(lambda p: b.delete_version(p["job_id"], p["version_id"]))),
            # configurações
            "config_update": ("settings", lambda p: self.update_config(p["changes"])),
            "list_save": ("settings", lambda p: self.save_list(p["name"], p["items"])),
            "config_export": ("settings", lambda p: self.export_config()),
            "config_import": ("settings", critical(lambda p: self.import_config(p["data"]))),
            "config_restore": ("settings", critical(lambda p: self.store.restore_config_version(p["filename"]))),
            "note_save": ("settings", lambda p: self.save_note(p)),
            "note_delete": ("settings", lambda p: self.delete_note(p["id"])),
            "profile_save": ("settings", lambda p: s.save_profile(p["name"], p.get("permissions", []), p.get("pin", ""))),
            "profile_delete": ("settings", lambda p: s.delete_profile(p["name"])),
            "password_set": ("settings", lambda p: s.set_critical_password(p.get("new", ""), p.get("current", ""))),
            "pairing_revoke": ("settings", lambda p: s.revoke_all(self.port)),
            "shutdown": ("settings", lambda p: {"stopping": True}),
        }

    def dispatch(self, command: str, payload: dict):
        table = self.actions()
        if command not in table:
            raise LookupError("Ação desconhecida.")
        permission, function = table[command]
        if not self.security.allowed(permission):
            raise PermissionError(f"O perfil ativo não tem a permissão '{PERMISSIONS[permission]}'.")
        return function(payload)


# ----------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    app: App = None            # preenchido em make_server()
    server_version = f"{APP_NAME}/{VERSION}"

    def log_message(self, fmt, *args):           # silencia o log padrão no terminal
        pass

    # --- utilitários --------------------------------------------------
    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin in self.app.allowed_origins()

    def _host_ok(self) -> bool:
        """Proteção contra DNS rebinding: só aceita Host 127.0.0.1/localhost."""
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _cors(self) -> None:
        origin = self.headers.get("Origin")
        if origin and origin in self.app.allowed_origins():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Private-Network", "true")

    def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8",
              extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self._cors()
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _authorized(self) -> bool:
        return self.app.security.check_token(self.headers.get("Authorization", ""))

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("Requisição muito grande.")
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(data, dict):
            raise ValueError("Corpo JSON inválido.")
        return data

    # --- métodos HTTP -------------------------------------------------
    def do_OPTIONS(self):
        """Pré-verificação CORS feita pelo navegador antes das chamadas da Vercel."""
        if not self._host_ok() or not self._origin_ok():
            return self._error(403, "Origem não autorizada.")
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self._host_ok():
            return self._error(403, "Host não permitido.")
        path = urlparse(self.path).path
        if path.startswith("/api/") and not self._origin_ok():
            return self._error(403, "Origem web não autorizada. Configure a URL do site nas Configurações.")
        if path == "/api/ping":
            return self._json(200, {"ok": True, "name": APP_NAME, "version": VERSION, "pid": os.getpid()})
        if path.startswith("/api/download/"):
            return self._download(path)
        if path.startswith("/api/"):
            return self._error(404, "Rota não encontrada.")
        return self._static(path)

    def do_POST(self):
        if not self._host_ok():
            return self._error(403, "Host não permitido.")
        if not self._origin_ok():
            return self._error(403, "Origem web não autorizada.")
        path = urlparse(self.path).path
        try:
            payload = self._body()
            if path == "/api/pair":
                return self._json(200, {"token": self.app.security.pair(str(payload.get("code", "")))})
            if not self._authorized():
                return self._error(401, "Não autorizado. Abra o site pelo atalho do OrganizaLocal ou faça o pareamento.")
            match = re.fullmatch(r"/api/action/([a-z_]+)", path)
            if not match:
                return self._error(404, "Rota não encontrada.")
            command = match.group(1)
            result = self.app.dispatch(command, payload)
            self._json(200, {"ok": True, "result": result})
            if command == "shutdown":
                threading.Thread(target=self.server.shutdown, daemon=True).start()
        except LookupError as exc:
            self._error(404, str(exc))
        except PermissionError as exc:
            self._error(403, friendly_error(exc) if getattr(exc, "errno", None) else str(exc))
        except (ValueError, KeyError, FileExistsError, RuntimeError, OSError) as exc:
            message = f"Campo obrigatório ausente: {exc}" if isinstance(exc, KeyError) else friendly_error(exc)
            self._error(400, message)
        except Exception as exc:                       # erro inesperado: registra e responde 500
            self.app.store.event("api_error", "error", reason=repr(exc), path=path)
            self._error(500, "Erro interno. Consulte o histórico.")

    def _download(self, path: str):
        if not self._authorized():
            return self._error(401, "Não autorizado.")
        match = re.fullmatch(r"/api/download/(reports|exports)/([\w.\-]+)", path)
        if not match:
            return self._error(404, "Arquivo não encontrado.")
        folder = (self.app.store.root / match.group(1)).resolve()
        target = (folder / match.group(2)).resolve()
        if target.parent != folder or not target.is_file():
            return self._error(404, "Arquivo não encontrado.")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), ctype,
                   {"Content-Disposition": f'attachment; filename="{target.name}"'})

    def _static(self, path: str):
        root = web_directory().resolve()
        target = (root / (path.lstrip("/") or "index.html")).resolve()
        if target.is_dir():
            target = target / "index.html"
        if root not in target.parents or not target.is_file():      # bloqueia "../" fora de web/
            return self._error(404, "Arquivo não encontrado.")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)


def make_server(app: App, port: int | None = None) -> ThreadingHTTPServer:
    """Cria o servidor ligado somente a 127.0.0.1."""
    handler = type("BoundHandler", (Handler,), {"app": app})
    server = ThreadingHTTPServer(("127.0.0.1", port if port is not None else app.port), handler)
    server.daemon_threads = True
    return server

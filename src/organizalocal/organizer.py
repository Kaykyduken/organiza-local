"""Motor de organização: simulação, movimentação segura e ferramentas de arquivos.

Atende HU06–HU12 / RF07–RF14 e RNF01, RNF03, RNF04, RNF05, RNF09 e RNF10.

Conceitos de SO usados aqui:
  * Percorrer diretórios (os.walk) sem seguir links simbólicos.
  * Metadados do sistema de arquivos (os.stat: tamanho, datas, dispositivo).
  * Permissões (os.access) antes de ler/gravar.
  * Mover no mesmo disco = os.rename (o kernel só troca a entrada do diretório,
    nenhum byte é copiado); entre discos diferentes = cópia + SHA-256 + exclusão.
  * Tratamento de erros do SO: arquivo em uso, sem permissão, disco cheio...
"""
from __future__ import annotations

import copy
import errno
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
from pathlib import Path

from . import rules as R
from .storage import Store, now, sha256

MAX_FILES = 25000          # limite de arquivos por varredura (proteção contra pastas gigantes)

# Rótulos usados no histórico e na interface.
ACTION_LABELS = {
    "move": "Mover", "default": "Mover (destino padrão)", "quarantine": "Quarentena",
    "exception": "Exceção — não mover", "tie": "Empate de prioridade — revisar",
    "suspicious": "Formato disfarçado — revisar",
    "conflict": "Já existe no destino", "no_match": "Nenhuma regra", "busy": "Em uso/incompleto",
    "excluded": "Excluído/protegido", "already": "Já está no destino", "error": "Erro",
}


def under(path, parent) -> bool:
    """True se `path` estiver dentro de `parent` (ou for igual)."""
    try:
        Path(path).expanduser().resolve().relative_to(Path(parent).expanduser().resolve())
        return True
    except (ValueError, OSError):
        return False


def friendly_error(exc: BaseException) -> str:
    """Traduz erros do sistema operacional para mensagens claras (RNF09)."""
    winerror = getattr(exc, "winerror", None)
    if winerror in (32, 33):
        return "Arquivo em uso por outro programa (feche-o e tente novamente)."
    if isinstance(exc, PermissionError) or getattr(exc, "errno", None) in (errno.EACCES, errno.EPERM):
        return "Sem permissão para acessar o arquivo ou a pasta."
    if isinstance(exc, FileNotFoundError) or getattr(exc, "errno", None) == errno.ENOENT:
        return "Arquivo ou pasta não encontrado (pode ter sido movido ou apagado)."
    if getattr(exc, "errno", None) == errno.ENOSPC:
        return "Sem espaço livre no disco de destino."
    if isinstance(exc, FileExistsError):
        return f"Já existe um arquivo com esse nome no destino: {exc}"
    return str(exc) or exc.__class__.__name__


class Organizer:
    """Aplica as regras às pastas monitoradas."""

    def __init__(self, store: Store):
        self.store = store
        self.run_lock = threading.Lock()   # impede duas organizações ao mesmo tempo

    @property
    def config(self) -> dict:
        return self.store.config

    # ------------------------------------------------------------------
    # Proteções e permissões (RNF03)
    # ------------------------------------------------------------------
    def protected(self, path, is_dir: bool = False) -> bool:
        """A pasta de dados e os caminhos protegidos nunca são tocados automaticamente."""
        p = Path(path).expanduser()
        if under(p, self.store.root) or (is_dir and under(self.store.root, p)):
            return True
        for item in self.config.get("protected_paths", []):
            if item and (under(p, item) or (is_dir and under(item, p))):
                return True
        return False

    def excluded(self, path) -> bool:
        """Exclusões globais por caminho, nome exato ou extensão."""
        p = Path(path)
        if self.protected(p):
            return True
        ex = self.config.get("exclusions", {})
        if any(under(p, q) for q in ex.get("paths", []) if q):
            return True
        if p.name.casefold() in [str(n).casefold() for n in ex.get("names", [])]:
            return True
        return R.extension(p) in [R.normalize_extension(e) for e in ex.get("extensions", []) if e]

    @staticmethod
    def can_read(path) -> bool:
        return Path(path).is_file() and os.access(path, os.R_OK)

    @staticmethod
    def can_write_dir(path) -> bool:
        """Sobe até a primeira pasta existente e verifica permissão de escrita."""
        test = Path(path).expanduser()
        while not test.exists() and test != test.parent:
            test = test.parent
        return test.is_dir() and os.access(test, os.W_OK)

    # ------------------------------------------------------------------
    # CRUD de regras (HU06–HU09, HU04)
    # ------------------------------------------------------------------
    def rule_by_id(self, rule_id: str) -> dict:
        rule = next((r for r in self.config["rules"] if r.get("id") == rule_id), None)
        if not rule:
            raise ValueError("Regra não encontrada.")
        return rule

    def validate(self, rule: dict) -> list[str]:
        return R.validate_rule(rule, is_protected=lambda p: self.protected(p, is_dir=True),
                               can_write=self.can_write_dir)

    def save_rule(self, payload: dict, rule_id: str | None = None) -> dict:
        """Cria (rule_id vazio) ou edita (HU07) uma regra, validando antes de salvar."""
        rule = R.normalize_rule(payload)
        errors = self.validate(rule)
        if errors:
            raise ValueError(" ".join(errors))
        with self.store.lock:
            rules = self.config["rules"]
            index = next((i for i, r in enumerate(rules) if r.get("id") == rule_id), None) if rule_id else None
            rule["id"] = rule_id if index is not None else secrets.token_hex(6)
            if index is None:
                rules.append(rule)
            else:
                rules[index] = rule
            self.store.save_config()
        self.store.event("rule_save", "ok", rule_id=rule["id"], rule_name=rule["name"],
                         detail="editada" if index is not None else "criada")
        return rule

    def delete_rule(self, rule_id: str) -> dict:
        """HU08 — a confirmação é pedida pela interface antes de chamar este método."""
        with self.store.lock:
            rule = self.rule_by_id(rule_id)
            self.config["rules"] = [r for r in self.config["rules"] if r.get("id") != rule_id]
            self.store.save_config()
        self.store.event("rule_delete", "ok", rule_id=rule_id, rule_name=rule.get("name"))
        return {"deleted": rule_id}

    def duplicate_rule(self, rule_id: str) -> dict:
        source = copy.deepcopy(self.rule_by_id(rule_id))
        source.pop("id", None)
        source["name"] = source.get("name", "Regra") + " (cópia)"
        source["enabled"] = False          # a cópia nasce desativada para não empatar
        return self.save_rule(source)

    def set_enabled(self, rule_id: str, enabled: bool) -> dict:
        """HU09 — ativa/desativa sem excluir; o estado fica salvo."""
        with self.store.lock:
            rule = self.rule_by_id(rule_id)
            rule["enabled"] = bool(enabled)
            self.store.save_config()
        self.store.event("rule_toggle", "ok", rule_id=rule_id, rule_name=rule["name"],
                         detail="ativada" if enabled else "desativada")
        return rule

    def change_priority(self, rule_id: str, delta: int | None = None, value: int | None = None) -> dict:
        """HU04 — aumenta/diminui (delta ±1) ou define a prioridade (0–10)."""
        with self.store.lock:
            rule = self.rule_by_id(rule_id)
            new = int(value) if value is not None else int(rule.get("priority", 0)) + int(delta or 0)
            rule["priority"] = max(0, min(10, new))
            self.store.save_config()
        self.store.event("rule_priority", "ok", rule_id=rule_id, rule_name=rule["name"],
                         detail=f"prioridade {rule['priority']}")
        return rule

    def ordered_rules(self) -> list[dict]:
        """HU04/HU06 — lista ordenada por prioridade (maior primeiro)."""
        return sorted(self.config["rules"], key=lambda r: (-int(r.get("priority", 0)), r.get("name", "")))

    def validate_all(self) -> list[dict]:
        """Problemas em regras + possíveis empates + pastas monitoradas inexistentes."""
        problems = [{"rule": r.get("name"), "error": e}
                    for r in self.config["rules"] for e in self.validate(r)]
        for item in R.overlapping_rules(self.config["rules"]):
            problems.append({"rule": " × ".join(item["rules"]),
                             "error": f"Mesma prioridade ({item['priority']}) e condições que podem "
                                      f"coincidir ({item['detail']}). Arquivos assim irão para revisão."})
        for folder in self.config.get("watch_dirs", []):
            if not Path(folder).is_dir():
                problems.append({"rule": "Pastas monitoradas", "error": f"Pasta indisponível: {folder}"})
        return problems

    # ------------------------------------------------------------------
    # Varredura das pastas monitoradas
    # ------------------------------------------------------------------
    def scan(self, paths=None, recursive: bool | None = None):
        """Gera os arquivos das pastas monitoradas (padrão: Downloads)."""
        paths = paths or self.config.get("watch_dirs", [])
        recursive = self.config.get("recursive", False) if recursive is None else recursive
        count = 0
        for source in paths:
            root = Path(source).expanduser()
            if root.is_file():
                if not root.is_symlink() and not self.excluded(root):
                    yield root
                continue
            if not root.is_dir() or self.protected(root, is_dir=True):
                continue
            # Destinos das regras que ficam dentro da pasta monitorada não são reprocessados.
            skip_dirs = [r.get("destination") for r in self.config["rules"] if r.get("destination")]
            for directory, folders, files in os.walk(root, followlinks=False):
                parent = Path(directory)
                folders.sort()
                files.sort()
                folders[:] = [d for d in folders
                              if not (parent / d).is_symlink()
                              and not self.protected(parent / d, is_dir=True)
                              and not any(under(parent / d, q) for q in skip_dirs)
                              and not self.excluded(parent / d)]
                for filename in files:
                    file = parent / filename
                    if file.is_symlink() or self.excluded(file):
                        continue
                    yield file
                    count += 1
                    if count >= MAX_FILES:
                        return
                if not recursive:
                    folders.clear()     # apenas o primeiro nível

    def busy_reason(self, file: Path) -> str | None:
        """Detecta arquivos temporários, ocultos, muito recentes ou sem permissão de leitura."""
        if R.extension(file) in R.TEMP_SUFFIX or file.name.startswith("~$"):
            return "Arquivo temporário ou download em andamento."
        if file.name.startswith(".") or file.name.lower() in ("desktop.ini", "thumbs.db"):
            return "Arquivo oculto/do sistema."
        try:
            st = file.stat()
        except OSError as exc:
            return friendly_error(exc)
        min_age = int(self.config.get("min_file_age_seconds", 30))
        if time.time() - st.st_mtime < min_age:
            return f"Modificado há menos de {min_age} s (pode estar sendo baixado)."
        if not self.can_read(file):
            return "Sem permissão de leitura."
        return None

    # ------------------------------------------------------------------
    # Decisão por arquivo (usada pela simulação e pela execução)
    # ------------------------------------------------------------------
    def decide(self, file, only_rule: str | None = None, sequence: int = 1) -> dict:
        file = Path(file)
        row = {"source": str(file), "name": file.name, "destination": "", "action": "no_match",
               "rule_id": "", "rule_name": "", "matched": [], "reason": "",
               "category": R.category(file, self.config.get("categories")),
               "format": R.detect_format(file)}
        try:
            row["bytes"] = file.stat().st_size
        except OSError:
            row["bytes"] = 0
        if self.excluded(file):
            row.update(action="excluded", reason="Caminho protegido ou na lista de exclusões.")
            return row
        busy = self.busy_reason(file)
        if busy:
            row.update(action="busy", reason=busy)
            return row
        disguised = R.is_disguised(file)
        if disguised and not self.config.get("quarantine_risky") and not only_rule:
            # Conteúdo executável com extensão de outro tipo (ex.: "foto.jpg" que é .exe):
            # nunca é movido em silêncio — vai para a fila de revisão.
            row.update(action="suspicious", reason="O conteúdo é um executável, mas a extensão diz outra coisa.")
            return row
        if self.config.get("quarantine_risky") and not only_rule:
            if R.extension(file) in R.RISKY or disguised:
                row.update(action="quarantine",
                           destination=str(self.store.root / "quarantine" / R.clean_name(file.name)),
                           reason="Conteúdo executável com extensão disfarçada." if disguised
                           else "Extensão potencialmente perigosa.")
                return row

        result = R.evaluate(file, self.config["rules"], self.config.get("categories"), only_rule)
        row["matched"] = [{"id": r["id"], "name": r["name"], "priority": r.get("priority", 0)}
                          for r in result["matched"]]
        if result["tie"]:
            names = ", ".join(m["name"] for m in row["matched"] if m["priority"] == row["matched"][0]["priority"])
            row.update(action="tie", reason=f"Empate de prioridade entre: {names}.")
            return row
        rule = result["rule"]
        if rule:
            row.update(rule_id=rule["id"], rule_name=rule["name"])
            if result["conflict"]:
                row["reason"] = (f"{len(result['matched'])} regras correspondem; "
                                 f"vale a de maior prioridade ({rule['name']}).")
            destination = rule.get("destination")
            project = next((p for p in self.config.get("projects", []) if p.get("id") == rule.get("project_id")), None)
            if project:
                destination = project.get("directory") or destination
            exc = result["exception"]
            if exc:
                if exc.get("action") == "skip":
                    row.update(action="exception",
                               reason=f"Exceção: {exc.get('description') or 'condição de exceção atendida'}.")
                    return row
                destination = exc.get("destination") or destination
                row["reason"] = f"Exceção redirecionou para {destination}."
            pattern = rule.get("rename_pattern") or self.config.get("rename_pattern", "")
            target = Path(destination).expanduser() / R.render_name(file, pattern, sequence)
            action = "move"
        elif self.config.get("default_destination") and not only_rule:
            target = Path(self.config["default_destination"]).expanduser() / R.clean_name(file.name)
            action = "default"
        else:
            row["reason"] = row["reason"] or "Nenhuma regra ativa corresponde."
            return row

        if target.resolve() == file.resolve():
            row.update(action="already", reason="O arquivo já está no destino.")
            return row
        row.update(action=action, destination=str(target))
        if target.exists():
            row["conflict_existing"] = True     # tratado conforme a política (RNF10)
        return row

    # ------------------------------------------------------------------
    # HU10 — simulação: NÃO move nem modifica nada
    # ------------------------------------------------------------------
    def simulate(self, paths=None, only_rule: str | None = None) -> dict:
        rows = []
        policy = self.config.get("conflict_policy", "rename")
        for sequence, file in enumerate(self.scan(paths), 1):
            try:
                row = self.decide(file, only_rule, sequence)
                if row.get("conflict_existing"):
                    row["action"] = "conflict"
                    row["reason"] = {"rename": "Já existe: será salvo com nome numerado.",
                                     "review": "Já existe: irá para a fila de revisão.",
                                     "skip": "Já existe: será ignorado."}[policy]
                    if policy == "rename":
                        row["destination"] = str(self._unique(Path(row["destination"])))
                rows.append(row)
            except (OSError, ValueError) as exc:
                rows.append({"source": str(file), "name": file.name, "action": "error",
                             "reason": friendly_error(exc), "destination": ""})
        summary = {key: sum(1 for r in rows if r["action"] == key) for key in ACTION_LABELS}
        return {"timestamp": now(), "count": len(rows), "summary": summary,
                "would_move": summary["move"] + summary["default"] + (summary["conflict"] if policy == "rename" else 0),
                "rows": rows, "policy": policy}

    # ------------------------------------------------------------------
    # HU11/HU12 — execução da organização
    # ------------------------------------------------------------------
    def organize(self, paths=None, only_rule: str | None = None, conflict: str | None = None,
                 trigger: str = "manual") -> dict:
        conflict = conflict or self.config.get("conflict_policy", "rename")
        if conflict not in ("rename", "review", "skip"):
            raise ValueError("Política de conflito inválida.")
        if not self.run_lock.acquire(blocking=False):
            raise RuntimeError("Já existe uma organização em andamento.")
        run_id = secrets.token_hex(6)
        result = {"run_id": run_id, "trigger": trigger, "started": now(), "processed": 0,
                  "moved": 0, "quarantined": 0, "reviewed": 0, "skipped": 0, "errors": [],
                  "moves": []}
        try:
            for sequence, file in enumerate(self.scan(paths), 1):
                result["processed"] += 1
                try:
                    row = self.decide(file, only_rule, sequence)
                    action = row["action"]
                    if action in ("tie", "suspicious"):
                        self.add_review(file, None, "priority_tie" if action == "tie" else "suspicious", row["reason"])
                        result["reviewed"] += 1
                        continue
                    if action not in ("move", "default", "quarantine"):
                        result["skipped"] += 1
                        continue
                    target = Path(row["destination"])
                    if action == "quarantine":
                        target = self._unique(target)
                    elif target.exists():
                        if conflict == "rename":
                            target = self._unique(target)
                        elif conflict == "review":
                            self.add_review(file, target, "name_conflict", "Já existe um arquivo com esse nome.",
                                            row["rule_id"])
                            result["reviewed"] += 1
                            continue
                        else:
                            result["skipped"] += 1
                            continue
                    info = self.transfer(file, target, internal=(action == "quarantine"),
                                         operation="quarantine" if action == "quarantine" else "move",
                                         rule_id=row["rule_id"], rule_name=row["rule_name"], run_id=run_id)
                    result["moves"].append(info)
                    if action == "quarantine":
                        result["quarantined"] += 1
                    else:
                        result["moved"] += 1
                except Exception as exc:   # cada falha é registrada; o resto continua (RNF04)
                    result["errors"].append({"file": str(file), "reason": friendly_error(exc)})
            result["finished"] = now()
            result["status"] = "ok" if not result["errors"] else ("partial" if result["moved"] else "error")
            self.config["last_runs"]["organize"] = result["finished"]
            self.store.save_config(snapshot=False)
            self.store.event("organize", result["status"], run_id=run_id, trigger=trigger,
                             **{k: result[k] for k in ("processed", "moved", "quarantined", "reviewed", "skipped")},
                             failures=len(result["errors"]),
                             errors=result["errors"][:50])
            return result
        finally:
            self.run_lock.release()

    @staticmethod
    def _unique(target: Path) -> Path:
        """Gera 'nome (1).ext', 'nome (2).ext'... sem sobrescrever nada (RNF10)."""
        target = Path(target)
        if not target.exists():
            return target
        ext = R.extension(target)
        stem = target.name[: -len(ext)] if ext else target.name
        for i in range(1, 10000):
            candidate = target.with_name(R.clean_name(f"{stem} ({i}){ext}"))
            if not candidate.exists():
                return candidate
        raise ValueError("Não foi possível gerar um nome livre no destino.")

    # ------------------------------------------------------------------
    # Movimentação segura (RNF04, RNF05, RNF09, RNF10)
    # ------------------------------------------------------------------
    def transfer(self, source, target, *, overwrite: bool = False, operation: str = "move",
                 internal: bool = False, rule_id: str = "", rule_name: str = "", run_id: str = "") -> dict:
        """Move (ou copia) um arquivo garantindo que o conteúdo não muda.

        1. Verifica proteções e permissões.
        2. Calcula o SHA-256 da origem.
        3. Mesmo disco -> os.rename (atômico).  Discos diferentes -> cópia temporária,
           confere o hash, troca com os.replace e só então apaga a origem.
        4. Confere o hash no destino; se divergir, desfaz.
        5. Registra no histórico. Em caso de erro, registra a falha e propaga.
        """
        source = Path(source).expanduser().resolve()
        target = Path(target).expanduser()
        target = target.parent.resolve() / target.name if target.parent.exists() else target.absolute()
        moving = operation in ("move", "quarantine", "undo", "review", "rename")
        prior = None
        try:
            if not source.is_file() or source.is_symlink():
                raise FileNotFoundError(f"Origem indisponível: {source}")
            internal_areas = [self.store.root / q for q in ("quarantine", "backups", "protected_versions", "sandboxes")]
            if self.protected(source) and not (internal and any(under(source, a) for a in internal_areas)):
                raise PermissionError("Origem protegida.")
            if self.protected(target) and not (internal and any(under(target, a) for a in internal_areas)):
                raise PermissionError("Destino protegido.")
            if source == target:
                raise ValueError("Origem e destino são o mesmo arquivo.")
            if not self.can_read(source) or not self.can_write_dir(target.parent) \
                    or (moving and not self.can_write_dir(source.parent)):
                raise PermissionError("Permissões de leitura/escrita insuficientes.")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and not overwrite:
                raise FileExistsError(str(target))

            digest = sha256(source)
            size = source.stat().st_size
            # Antes de substituir algo, guarda uma cópia do arquivo existente.
            if target.exists():
                prior = self.store.root / "protected_versions" / f"{secrets.token_hex(6)}_{R.clean_name(target.name)}"
                shutil.copy2(target, prior)

            same_device = source.stat().st_dev == target.parent.stat().st_dev
            if moving and same_device:
                method = "rename"
                if overwrite:
                    os.replace(source, target)
                else:
                    os.rename(source, target)
                if sha256(target) != digest:              # nunca deveria acontecer
                    os.rename(target, source)
                    raise IOError("SHA-256 divergente após mover; operação desfeita.")
            else:
                method = "copy+sha256"
                fd, temp_name = tempfile.mkstemp(prefix=".organiza_", dir=target.parent)
                os.close(fd)
                temporary = Path(temp_name)
                try:
                    shutil.copy2(source, temporary)       # copia conteúdo e datas
                    if sha256(temporary) != digest:
                        raise IOError("Falha de integridade (SHA-256) na cópia temporária.")
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
                if sha256(target) != digest:
                    target.unlink(missing_ok=True)
                    raise IOError("Falha de integridade (SHA-256) no destino.")
                if moving:
                    try:
                        source.unlink()
                    except OSError:
                        # Origem presa (ex.: aberta no Windows): desfaz a cópia para não duplicar.
                        target.unlink(missing_ok=True)
                        if prior:
                            shutil.copy2(prior, target)
                        raise
            info = {"source": str(source), "destination": str(target), "sha256": digest, "bytes": size,
                    "method": method, "prior": str(prior) if prior else "", "rule_id": rule_id,
                    "rule_name": rule_name}
            self.store.event(operation, "ok", run_id=run_id, **info)
            return info
        except Exception as exc:
            self.store.event(operation, "error", source=str(source), destination=str(target),
                             reason=friendly_error(exc), rule_id=rule_id, rule_name=rule_name, run_id=run_id)
            raise

    # ------------------------------------------------------------------
    # Fila de revisão (empates e conflitos de nome)
    # ------------------------------------------------------------------
    def add_review(self, source, target, reason: str, detail: str = "", rule_id: str = "") -> dict:
        with self.store.lock:
            rows = self.store.read(self.store.review_path, [])
            item = {"id": secrets.token_hex(6), "source": str(source), "destination": str(target or ""),
                    "reason": reason, "detail": detail, "rule_id": rule_id, "timestamp": now()}
            if not any(r["source"] == item["source"] and r["reason"] == reason for r in rows):
                rows.append(item)
                self.store.write(self.store.review_path, rows)
                self.store.event("review", "pending", source=str(source), destination=str(target or ""),
                                 reason=detail or reason)
            return item

    def review_list(self) -> list[dict]:
        rows = self.store.read(self.store.review_path, [])
        alive = [r for r in rows if Path(r["source"]).exists()]
        if len(alive) != len(rows):
            self.store.write(self.store.review_path, alive)
        return alive

    def resolve_review(self, review_id: str, decision: str, destination: str = "", confirm: bool = False) -> dict:
        """Decisões: move | rename (nome numerado) | replace (com confirmação) | quarantine | ignore."""
        with self.store.lock:
            rows = self.store.read(self.store.review_path, [])
            item = next((r for r in rows if r["id"] == review_id), None)
            if not item:
                raise ValueError("Item da fila de revisão não encontrado.")
            source = Path(item["source"])
            target_text = destination or item.get("destination")
            if decision == "ignore":
                result = {"ignored": str(source)}
            elif decision == "quarantine":
                result = self.transfer(source, self._unique(self.store.root / "quarantine" / source.name),
                                       internal=True, operation="quarantine")
            elif decision in ("move", "rename", "replace"):
                if not target_text:
                    raise ValueError("Informe a pasta ou o caminho de destino.")
                target = Path(target_text).expanduser()
                if target.is_dir():
                    target = target / source.name
                if decision == "rename":
                    target = self._unique(target)
                if decision == "replace" and not confirm:
                    raise PermissionError("Confirme a substituição do arquivo existente.")
                result = self.transfer(source, target, overwrite=(decision == "replace"), operation="review")
            else:
                raise ValueError("Decisão inválida.")
            rows = [r for r in rows if r["id"] != review_id]
            self.store.write(self.store.review_path, rows)
            self.store.event("review_decision", "ok", source=str(source), detail=decision)
            return result

    # ------------------------------------------------------------------
    # Desfazer movimentação
    # ------------------------------------------------------------------
    def undo(self, event_id: str) -> dict:
        event = self.store.find_event(event_id)
        if not event or event.get("operation") not in ("move", "review", "rename") or event.get("status") != "ok":
            raise ValueError("Movimentação não encontrada no histórico.")
        current, original = Path(event["destination"]), Path(event["source"])
        if not current.exists() or sha256(current) != event.get("sha256"):
            raise ValueError("O arquivo no destino não existe mais ou foi alterado depois da movimentação.")
        if original.exists():
            original = self._unique(original)
        result = self.transfer(current, original, operation="undo")
        self.store.event("undo_reference", "ok", reference=event_id)
        return result

    # ------------------------------------------------------------------
    # Ferramentas extras (mantidas do projeto 0.9)
    # ------------------------------------------------------------------
    def rename_file(self, path: str, pattern: str, sequence: int = 1) -> dict:
        """Renomeia um arquivo usando um modelo de nome."""
        source = Path(path).expanduser().resolve()
        if not source.is_file() or self.protected(source):
            raise ValueError("Arquivo não encontrado ou protegido.")
        target = source.parent / R.render_name(source, pattern, int(sequence))
        if target == source:
            return {"unchanged": str(source)}
        if target.exists():
            raise FileExistsError(str(target))
        return self.transfer(source, target, operation="rename")

    def duplicates(self, paths=None) -> list[dict]:
        """Duplicados: primeiro agrupa por tamanho (barato) e só então calcula SHA-256."""
        by_size: dict[int, list[Path]] = {}
        for p in self.scan(paths, recursive=True):
            try:
                by_size.setdefault(p.stat().st_size, []).append(p)
            except OSError:
                continue
        by_hash: dict[str, list[str]] = {}
        for files in by_size.values():
            if len(files) < 2:
                continue
            for p in files:
                try:
                    by_hash.setdefault(sha256(p), []).append(str(p))
                except OSError:
                    continue
        groups = [{"sha256": h, "files": v, "bytes_each": Path(v[0]).stat().st_size}
                  for h, v in by_hash.items() if len(v) > 1]
        return sorted(groups, key=lambda g: -g["bytes_each"] * (len(g["files"]) - 1))

    def remove_duplicate(self, path: str, keep: str) -> dict:
        """Apaga uma cópia somente se `keep` existir e tiver o MESMO hash."""
        victim, survivor = Path(path).expanduser().resolve(), Path(keep).expanduser().resolve()
        if victim == survivor or not victim.is_file() or not survivor.is_file():
            raise ValueError("Informe dois arquivos diferentes que existam.")
        if self.protected(victim):
            raise PermissionError("Arquivo protegido.")
        digest = sha256(victim)
        if digest != sha256(survivor):
            raise ValueError("Os arquivos não são idênticos; nada foi apagado.")
        victim.unlink()
        self.store.event("duplicate_remove", "ok", source=str(victim), kept=str(survivor), sha256=digest)
        return {"deleted": str(victim), "kept": str(survivor)}

    def extension_inventory(self, paths=None, recursive: bool | None = None) -> dict:
        """Lê as pastas monitoradas e lista as extensões encontradas (para os checkboxes da regra).

        Para cada extensão devolve: quantidade de arquivos, tamanho total, categoria,
        até 3 nomes de exemplo e quais regras ATIVAS já usam essa extensão (ajuda a
        evitar empates de prioridade). Arquivos sem extensão são contados à parte.
        """
        found: dict[str, dict] = {}
        total = without_ext = temporary = 0
        for file in self.scan(paths, recursive):
            total += 1
            ext = R.extension(file)
            if not ext:
                without_ext += 1
                continue
            if ext in R.TEMP_SUFFIX:          # .crdownload, .part... downloads incompletos não viram opção
                temporary += 1
                continue
            item = found.setdefault(ext, {"ext": ext, "count": 0, "bytes": 0, "examples": [],
                                          "category": R.category(file, self.config.get("categories"))})
            item["count"] += 1
            try:
                item["bytes"] += file.stat().st_size
            except OSError:
                pass
            if len(item["examples"]) < 3:
                item["examples"].append(file.name)
        # Quais regras ativas já usam cada extensão
        used: dict[str, list[dict]] = {}
        for rule in self.config["rules"]:
            if rule.get("enabled", True):
                for ext in rule.get("conditions", {}).get("extensions", []):
                    used.setdefault(ext, []).append({"id": rule["id"], "name": rule["name"],
                                                     "priority": rule.get("priority", 0)})
        items = sorted(found.values(), key=lambda x: (-x["count"], x["ext"]))
        for item in items:
            item["used_by"] = used.get(item["ext"], [])
        return {"folders": list(paths or self.config.get("watch_dirs", [])), "total_files": total,
                "without_extension": without_ext, "temporary": temporary, "extensions": items, "used_by": used,
                "timestamp": now()}

    def suggestions(self, paths=None) -> list[dict]:
        """Classificação heurística: sugere categoria/destino para arquivos sem regra."""
        out = []
        home = Path.home()
        for file in self.scan(paths):
            if self.busy_reason(file):
                continue
            result = R.evaluate(file, self.config["rules"], self.config.get("categories"))
            if result["matched"]:
                continue
            cat = R.category(file, self.config.get("categories"))
            fmt = R.detect_format(file)
            words = [w for w in re.split(r"[\s_\-.()\[\]]+", file.stem.lower()) if len(w) >= 4 and not w.isdigit()]
            out.append({"file": str(file), "category": cat, "format": R.FORMAT_LABELS.get(fmt, fmt),
                        "extension": R.extension(file),
                        "suggested_destination": str(home / "Documents" / cat) if cat != "Outros" else "",
                        "keywords": words[:3],
                        "reason": f"Extensão {R.extension(file) or '(nenhuma)'}; formato real {R.FORMAT_LABELS.get(fmt, fmt)}."})
            if len(out) >= 300:
                break
        return out

    def integrity(self, path: str, expected: str = "") -> dict:
        p = Path(path).expanduser()
        if not p.is_file():
            raise ValueError("Arquivo não encontrado.")
        actual = sha256(p)
        return {"path": str(p), "sha256": actual, "expected": expected or None,
                "matches": (actual == expected.strip().lower()) if expected else None}

    # --- Quarentena: arquivos suspeitos nunca são executados -------------
    def quarantine_list(self) -> list[dict]:
        folder = self.store.root / "quarantine"
        return [{"name": p.name, "bytes": p.stat().st_size, "format": R.FORMAT_LABELS.get(R.detect_format(p), "?")}
                for p in sorted(folder.iterdir()) if p.is_file()]

    def quarantine_action(self, action: str, name: str, destination: str = "", confirm: bool = False) -> dict:
        folder = (self.store.root / "quarantine").resolve()
        source = (folder / name).resolve()
        if source.parent != folder or not source.is_file():
            raise ValueError("Arquivo não encontrado na quarentena.")
        if not confirm:
            raise PermissionError("Esta ação exige confirmação.")
        if action == "delete":
            source.unlink()
            self.store.event("quarantine_delete", "ok", source=str(source))
            return {"deleted": name}
        if action != "release" or not destination:
            raise ValueError("Informe a pasta para onde liberar o arquivo.")
        target = Path(destination).expanduser()
        if target.is_dir():
            target = target / source.name
        return self.transfer(source, self._unique(target), internal=True, operation="quarantine_release")

    # --- Sandbox: testa as regras com CÓPIAS, sem tocar nos originais ------
    def sandbox_run(self, paths=None, limit: int = 200) -> dict:
        sandbox_id = secrets.token_hex(6)
        root = self.store.root / "sandboxes" / sandbox_id
        initial, output = root / "entrada", root / "saida"
        initial.mkdir(parents=True)
        output.mkdir()
        copied = 0
        for file in self.scan(paths):
            if copied >= limit:
                break
            target = self._unique(initial / file.name)
            shutil.copy2(file, target)
            os.utime(target, (time.time() - 3600, time.time() - 3600))  # evita "arquivo recente"
            copied += 1
        results = []
        for file in sorted(initial.iterdir()):
            res = R.evaluate(file, self.config["rules"], self.config.get("categories"))
            if res["tie"]:
                results.append({"file": file.name, "rule": "", "output": "", "note": "empate → revisão"})
                continue
            rule = res["rule"]
            if not rule:
                results.append({"file": file.name, "rule": "", "output": "", "note": "sem regra"})
                continue
            if res["exception"] and res["exception"].get("action") == "skip":
                results.append({"file": file.name, "rule": rule["name"], "output": "", "note": "exceção"})
                continue
            folder = output / R.clean_name(rule["name"])
            folder.mkdir(exist_ok=True)
            dest = self._unique(folder / file.name)
            shutil.copy2(file, dest)
            results.append({"file": file.name, "rule": rule["name"], "output": str(dest), "note": "movido no sandbox"})
        self.store.event("sandbox", "ok", sandbox_id=sandbox_id, files=copied)
        return {"id": sandbox_id, "path": str(root), "files": copied, "results": results}

    def sandbox_list(self) -> list[dict]:
        folder = self.store.root / "sandboxes"
        return [{"id": p.name, "path": str(p), "files": len(list((p / "entrada").glob("*")))}
                for p in sorted(folder.iterdir()) if p.is_dir()]

    def sandbox_delete(self, sandbox_id: str) -> dict:
        if not re.fullmatch(r"[0-9a-f]{12}", sandbox_id):
            raise ValueError("Identificador inválido.")
        shutil.rmtree(self.store.root / "sandboxes" / sandbox_id, ignore_errors=True)
        self.store.event("sandbox_delete", "ok", sandbox_id=sandbox_id)
        return {"deleted": sandbox_id}

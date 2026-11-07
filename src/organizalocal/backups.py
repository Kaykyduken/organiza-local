"""Backups por regras com versões e retenção (padrão: 5 versões).

Cada "regra de backup" (backup job) define:

    {
      "id": "9f8e7d", "name": "Faculdade", "enabled": true,
      "sources": ["C:/Users/kayky/Documents/Faculdade"],   # pastas ou arquivos
      "destination": "",              # vazio = <pasta de dados>/backups/<id>
      "mode": "zip",                  # zip (compactado) | copy (cópia de pastas)
      "include_extensions": [".docx", ".pdf"],   # vazio = todas
      "exclude_patterns": ["*.tmp", "node_modules"],
      "interval_hours": 24,           # de quanto em quanto tempo roda sozinho
      "max_versions": 5,              # versões mantidas (as travadas nunca são apagadas)
      "skip_unchanged": true          # não cria versão nova se nada mudou
    }

Cada execução gera uma versão (AAAAMMDD-HHMMSS) + um manifesto JSON com o SHA-256 de
cada arquivo, usado para comparar versões, verificar integridade e restaurar.

Conceitos de SO: cópia de arquivos e diretórios, compactação, preservação de
metadados (datas), retenção/limpeza de espaço em disco e abertura do gerenciador
de arquivos do sistema (explorer / xdg-open) via subprocess.
"""
from __future__ import annotations

import fnmatch
import os
import secrets
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from . import rules as R
from .organizer import Organizer, friendly_error, under
from .storage import Store, now, sha256


class Backups:
    def __init__(self, store: Store, organizer: Organizer):
        self.store = store
        self.organizer = organizer

    # ------------------------------------------------------------------
    # Regras de backup (CRUD)
    # ------------------------------------------------------------------
    @property
    def jobs(self) -> list[dict]:
        return self.store.config["backup_jobs"]

    def job(self, job_id: str) -> dict:
        job = next((j for j in self.jobs if j.get("id") == job_id), None)
        if not job:
            raise ValueError("Regra de backup não encontrada.")
        return job

    def save_job(self, payload: dict, job_id: str | None = None) -> dict:
        job = {
            "name": str(payload.get("name") or "Backup").strip()[:120],
            "enabled": bool(payload.get("enabled", True)),
            "sources": [str(Path(s).expanduser()) for s in payload.get("sources", []) if str(s).strip()],
            "destination": str(payload.get("destination") or "").strip(),
            "mode": payload.get("mode", "zip"),
            "include_extensions": [R.normalize_extension(e) for e in R._as_list(payload.get("include_extensions"))],
            "exclude_patterns": R._as_list(payload.get("exclude_patterns")),
            "interval_hours": float(payload.get("interval_hours") or 24),
            "max_versions": int(payload.get("max_versions") or self.store.config.get("default_max_versions", 5)),
            "skip_unchanged": bool(payload.get("skip_unchanged", True)),
        }
        errors = []
        if not job["sources"]:
            errors.append("Informe pelo menos uma pasta ou arquivo de origem.")
        for src in job["sources"]:
            if not Path(src).is_absolute():
                errors.append(f"Use caminho completo: {src}")
            elif not Path(src).exists():
                errors.append(f"Origem não encontrada: {src}")
            elif self.organizer.protected(src, is_dir=True):
                errors.append(f"A origem contém a pasta de dados do aplicativo: {src}")
        if job["mode"] not in ("zip", "copy"):
            errors.append("Modo inválido (use zip ou copy).")
        if not 1 <= job["max_versions"] <= 100:
            errors.append("O número máximo de versões deve ficar entre 1 e 100.")
        if not 0.1 <= job["interval_hours"] <= 24 * 90:
            errors.append("Intervalo deve ficar entre 0,1 hora e 90 dias.")
        if job["destination"]:
            dest = Path(job["destination"]).expanduser()
            if not dest.is_absolute():
                errors.append("O destino do backup deve ser um caminho completo.")
            elif any(under(dest, s) for s in job["sources"] if Path(s).is_dir()):
                errors.append("O destino não pode ficar dentro de uma pasta de origem (o backup copiaria a si mesmo).")
            elif not self.organizer.can_write_dir(dest):
                errors.append("Sem permissão de escrita no destino do backup.")
        if errors:
            raise ValueError(" ".join(errors))
        with self.store.lock:
            existing = next((j for j in self.jobs if j.get("id") == job_id), None) if job_id else None
            if existing:
                # Reduzir versões apaga as mais antigas: a interface pede confirmação.
                if job["max_versions"] < len(self.versions(job_id)) and not payload.get("confirm"):
                    raise PermissionError(f"Reduzir para {job['max_versions']} versões apagará as mais antigas "
                                          "(destravadas). Confirme a alteração.")
                existing.update(job)
                job = existing
            else:
                job["id"] = secrets.token_hex(6)
                job["last_run"] = ""
                self.jobs.append(job)
            self.store.save_config()
            if existing:
                self._trim(job)
        self.store.event("backup_job_save", "ok", job_id=job["id"], detail=job["name"])
        return job

    def delete_job(self, job_id: str, delete_files: bool = False) -> dict:
        job = self.job(job_id)
        with self.store.lock:
            self.store.config["backup_jobs"] = [j for j in self.jobs if j["id"] != job_id]
            self.store.save_config()
            index = self.index()
            versions = index.pop(job_id, [])
            if delete_files:
                for v in versions:
                    self._remove_version_files(v)
            self.store.write(self.store.backup_index_path, index)
        self.store.event("backup_job_delete", "ok", job_id=job_id, detail=job["name"])
        return {"deleted": job_id}

    # ------------------------------------------------------------------
    # Índice de versões
    # ------------------------------------------------------------------
    def index(self) -> dict:
        return self.store.read(self.store.backup_index_path, {})

    def versions(self, job_id: str) -> list[dict]:
        return self.index().get(job_id, [])

    def folder_for(self, job: dict) -> Path:
        if job.get("destination"):
            return Path(job["destination"]).expanduser() / f"OrganizaLocal-{R.clean_name(job['name'])}"
        return self.store.root / "backups" / job["id"]

    def is_due(self, job: dict) -> bool:
        if not job.get("enabled", True):
            return False
        last = job.get("last_run")
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
        except ValueError:
            return True
        return datetime.now(last_dt.tzinfo) - last_dt >= timedelta(hours=float(job.get("interval_hours", 24)))

    def next_run(self, job: dict) -> str:
        if not job.get("enabled", True):
            return ""
        last = job.get("last_run")
        if not last:
            return "na próxima verificação"
        try:
            return (datetime.fromisoformat(last) + timedelta(hours=float(job.get("interval_hours", 24)))
                    ).isoformat(timespec="minutes")
        except ValueError:
            return ""

    # ------------------------------------------------------------------
    # Execução de um backup
    # ------------------------------------------------------------------
    def _collect(self, job: dict) -> list[dict]:
        """Lista os arquivos das origens aplicando os filtros da regra."""
        dest_folder = self.folder_for(job)
        files = []
        for number, source in enumerate(job["sources"], 1):
            src = Path(source).expanduser()
            root_name = f"{number:02d}_{R.clean_name(src.name) or 'raiz'}"
            if src.is_file():
                candidates = [(src, src.name)]
            elif src.is_dir():
                candidates = []
                for directory, folders, names in os.walk(src, followlinks=False):
                    parent = Path(directory)
                    folders[:] = [d for d in folders
                                  if not (parent / d).is_symlink()
                                  and not under(parent / d, dest_folder)
                                  and not self.organizer.protected(parent / d, is_dir=True)
                                  and not any(fnmatch.fnmatch(d.lower(), p.lower()) for p in job["exclude_patterns"])]
                    for name in names:
                        path = parent / name
                        candidates.append((path, path.relative_to(src).as_posix()))
            else:
                continue
            for path, rel in candidates:
                if path.is_symlink() or self.organizer.protected(path):
                    continue
                if job["include_extensions"] and R.extension(path) not in job["include_extensions"]:
                    continue
                if any(fnmatch.fnmatch(path.name.lower(), p.lower()) or fnmatch.fnmatch(rel.lower(), p.lower())
                       for p in job["exclude_patterns"]):
                    continue
                try:
                    st = path.stat()
                    files.append({"root": root_name, "source_root": str(src), "rel": rel,
                                  "path": str(path), "bytes": st.st_size,
                                  "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                                  "sha256": sha256(path)})
                except OSError:
                    continue
        return files

    def run(self, job_id: str, trigger: str = "manual") -> dict:
        job = self.job(job_id)
        started = now()
        try:
            files = self._collect(job)
            previous = self.versions(job_id)
            signature = sorted((f["root"], f["rel"], f["sha256"]) for f in files)
            if job.get("skip_unchanged", True) and previous:
                last_manifest = self.manifest(job_id, previous[-1]["id"])
                old_sig = sorted((f["root"], f["rel"], f["sha256"]) for f in last_manifest.get("files", []))
                if old_sig == signature:
                    job["last_run"] = started
                    self.store.save_config(snapshot=False)
                    self.store.event("backup", "unchanged", job_id=job_id, detail=job["name"], trigger=trigger)
                    return {"job_id": job_id, "created": False, "reason": "Nada mudou desde a última versão.",
                            "files": len(files)}
            locked = sum(1 for v in previous if v.get("locked"))
            if locked >= int(job["max_versions"]):
                raise ValueError("Todas as vagas de versões estão ocupadas por versões travadas. "
                                 "Destrave uma versão ou aumente o máximo.")
            folder = self.folder_for(job)
            folder.mkdir(parents=True, exist_ok=True)
            version_id = datetime.now().strftime("%Y%m%d-%H%M%S")
            while (folder / f"{version_id}.zip").exists() or (folder / version_id).exists():
                version_id += "b"
            total = sum(f["bytes"] for f in files)
            # Confere espaço livre antes de gravar (conceito: armazenamento).
            free = shutil.disk_usage(folder).free
            if total > free:
                raise OSError(28, "Sem espaço livre suficiente no disco do backup.")

            if job["mode"] == "zip":
                final = folder / f"{version_id}.zip"
                temporary = folder / f".{version_id}.zip.tmp"
                with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                    for f in files:
                        archive.write(f["path"], arcname=f"{f['root']}/{f['rel']}")
                os.replace(temporary, final)
            else:
                final = folder / version_id
                temporary = folder / f".{version_id}.tmp"
                for f in files:
                    out = temporary / f["root"] / f["rel"]
                    out.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f["path"], out)
                    if sha256(out) != f["sha256"]:
                        raise IOError(f"SHA-256 divergente ao copiar {f['path']}")
                os.replace(temporary, final)

            manifest_path = folder / f"{version_id}.manifest.json"
            self.store.write(manifest_path, {"job_id": job_id, "job_name": job["name"], "version_id": version_id,
                                             "created": started, "mode": job["mode"],
                                             "sources": job["sources"], "files": files})
            version = {"id": version_id, "timestamp": started, "path": str(final), "mode": job["mode"],
                       "files": len(files), "bytes": total,
                       "stored_bytes": final.stat().st_size if final.is_file() else total,
                       "manifest": str(manifest_path), "locked": False, "trigger": trigger}
            with self.store.lock:
                index = self.index()
                index.setdefault(job_id, []).append(version)
                self.store.write(self.store.backup_index_path, index)
                job["last_run"] = started
                self.store.save_config(snapshot=False)
            removed = self._trim(job)
            self.store.event("backup", "ok", job_id=job_id, detail=job["name"], destination=str(final),
                             files=len(files), bytes=total, version_id=version_id, trigger=trigger,
                             removed_versions=removed)
            return {"job_id": job_id, "created": True, "version": version, "removed_versions": removed}
        except Exception as exc:
            for leftover in self.folder_for(job).glob(".*.tmp"):   # limpa gravações incompletas
                if leftover.is_dir():
                    shutil.rmtree(leftover, ignore_errors=True)
                else:
                    leftover.unlink(missing_ok=True)
            self.store.event("backup", "error", job_id=job_id, detail=job["name"], reason=friendly_error(exc),
                             trigger=trigger)
            raise

    def run_due(self) -> list[dict]:
        """Executa todas as regras de backup vencidas (chamado pelo agendador)."""
        results = []
        for job in list(self.jobs):
            if self.is_due(job):
                try:
                    results.append(self.run(job["id"], trigger="agendado"))
                except Exception as exc:
                    results.append({"job_id": job["id"], "error": friendly_error(exc)})
        return results

    # ------------------------------------------------------------------
    # Retenção (máximo de versões)
    # ------------------------------------------------------------------
    def _remove_version_files(self, version: dict) -> None:
        path = Path(version["path"])
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        if version.get("manifest"):
            Path(version["manifest"]).unlink(missing_ok=True)

    def _trim(self, job: dict) -> list[str]:
        """Apaga as versões mais antigas DESTRAVADAS até respeitar max_versions."""
        removed = []
        with self.store.lock:
            index = self.index()
            versions = index.get(job["id"], [])
            while len(versions) > int(job["max_versions"]):
                victim = next((v for v in versions if not v.get("locked")), None)
                if not victim:
                    break
                versions.remove(victim)
                self._remove_version_files(victim)
                removed.append(victim["id"])
            index[job["id"]] = versions
            self.store.write(self.store.backup_index_path, index)
        for vid in removed:
            self.store.event("backup_retention", "ok", job_id=job["id"], version_id=vid,
                             detail=f"versão antiga removida (máximo {job['max_versions']})")
        return removed

    def set_locked(self, job_id: str, version_id: str, locked: bool) -> dict:
        """Versão travada nunca é apagada pela retenção."""
        with self.store.lock:
            index = self.index()
            version = next((v for v in index.get(job_id, []) if v["id"] == version_id), None)
            if not version:
                raise ValueError("Versão não encontrada.")
            version["locked"] = bool(locked)
            self.store.write(self.store.backup_index_path, index)
        self.store.event("backup_lock", "ok", job_id=job_id, version_id=version_id,
                         detail="travada" if locked else "destravada")
        return version

    def delete_version(self, job_id: str, version_id: str) -> dict:
        with self.store.lock:
            index = self.index()
            version = next((v for v in index.get(job_id, []) if v["id"] == version_id), None)
            if not version:
                raise ValueError("Versão não encontrada.")
            if version.get("locked"):
                raise PermissionError("Destrave a versão antes de apagá-la.")
            index[job_id].remove(version)
            self._remove_version_files(version)
            self.store.write(self.store.backup_index_path, index)
        self.store.event("backup_delete", "ok", job_id=job_id, version_id=version_id)
        return {"deleted": version_id}

    # ------------------------------------------------------------------
    # Manifesto, comparação, verificação e restauração
    # ------------------------------------------------------------------
    def _version(self, job_id: str, version_id: str) -> dict:
        version = next((v for v in self.versions(job_id) if v["id"] == version_id), None)
        if not version:
            raise ValueError("Versão não encontrada.")
        return version

    def manifest(self, job_id: str, version_id: str) -> dict:
        version = self._version(job_id, version_id)
        return self.store.read(version["manifest"], {"files": []})

    def compare(self, job_id: str, version_a: str, version_b: str) -> dict:
        """Mostra arquivos adicionados, removidos e alterados entre duas versões."""
        a = {(f["root"], f["rel"]): f for f in self.manifest(job_id, version_a)["files"]}
        b = {(f["root"], f["rel"]): f for f in self.manifest(job_id, version_b)["files"]}
        key = lambda k: f"{k[0]}/{k[1]}"
        return {"a": version_a, "b": version_b,
                "added": sorted(key(k) for k in b.keys() - a.keys()),
                "removed": sorted(key(k) for k in a.keys() - b.keys()),
                "changed": sorted(key(k) for k in a.keys() & b.keys() if a[k]["sha256"] != b[k]["sha256"]),
                "unchanged": sum(1 for k in a.keys() & b.keys() if a[k]["sha256"] == b[k]["sha256"])}

    def verify(self, job_id: str, version_id: str) -> dict:
        """Recalcula o SHA-256 de cada arquivo guardado e compara com o manifesto."""
        version = self._version(job_id, version_id)
        files = self.manifest(job_id, version_id)["files"]
        bad = []
        if version["mode"] == "zip":
            import hashlib
            with zipfile.ZipFile(version["path"]) as archive:
                for f in files:
                    digest = hashlib.sha256()
                    try:
                        with archive.open(f"{f['root']}/{f['rel']}") as handle:
                            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                                digest.update(chunk)
                    except KeyError:
                        bad.append(f"{f['root']}/{f['rel']} (ausente)")
                        continue
                    if digest.hexdigest() != f["sha256"]:
                        bad.append(f"{f['root']}/{f['rel']}")
        else:
            for f in files:
                path = Path(version["path"]) / f["root"] / f["rel"]
                if not path.is_file() or sha256(path) != f["sha256"]:
                    bad.append(f"{f['root']}/{f['rel']}")
        status = "ok" if not bad else "error"
        self.store.event("backup_verify", status, job_id=job_id, version_id=version_id, failures=len(bad))
        return {"ok": not bad, "checked": len(files), "corrupted": bad}

    def restore(self, job_id: str, version_id: str, target_dir: str = "", only: list[str] | None = None,
                confirm: bool = False) -> dict:
        """Restaura uma versão.

        target_dir vazio -> volta cada arquivo ao local original. Se o arquivo atual for
                            diferente, uma cópia dele é guardada em protected_versions antes.
        target_dir       -> recria a estrutura dentro dessa pasta, sem sobrescrever nada.
        only             -> lista de caminhos "raiz/relativo" para restaurar só alguns arquivos.
        """
        if not confirm:
            raise PermissionError("Confirme a restauração.")
        version = self._version(job_id, version_id)
        files = self.manifest(job_id, version_id)["files"]
        if only:
            wanted = set(only)
            files = [f for f in files if f"{f['root']}/{f['rel']}" in wanted]
        restored, preserved, errors = [], [], []
        archive = zipfile.ZipFile(version["path"]) if version["mode"] == "zip" else None
        try:
            for f in files:
                inner = f"{f['root']}/{f['rel']}"
                try:
                    if target_dir:
                        dest = Organizer._unique(Path(target_dir).expanduser() / f["root"] / f["rel"])
                    else:
                        dest = Path(f["path"])                  # caminho original do arquivo
                    if self.organizer.protected(dest):
                        raise PermissionError("Destino protegido.")
                    if dest.exists():
                        if sha256(dest) == f["sha256"]:
                            continue                        # já idêntico, nada a fazer
                        keep = self.store.root / "protected_versions" / f"{secrets.token_hex(5)}_{dest.name}"
                        shutil.copy2(dest, keep)
                        preserved.append(str(keep))
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    temporary = dest.with_name(f".{dest.name}.{secrets.token_hex(3)}.restore")
                    if archive:
                        with archive.open(inner) as handle, open(temporary, "wb") as out:
                            shutil.copyfileobj(handle, out)
                    else:
                        shutil.copy2(Path(version["path"]) / f["root"] / f["rel"], temporary)
                    if sha256(temporary) != f["sha256"]:
                        temporary.unlink(missing_ok=True)
                        raise IOError("SHA-256 divergente no backup (arquivo corrompido).")
                    os.replace(temporary, dest)
                    restored.append(str(dest))
                except Exception as exc:
                    errors.append({"file": inner, "reason": friendly_error(exc)})
        finally:
            if archive:
                archive.close()
        status = "ok" if not errors else ("partial" if restored else "error")
        self.store.event("restore", status, job_id=job_id, version_id=version_id, files=len(restored),
                         preserved=len(preserved), failures=len(errors), destination=target_dir or "local original")
        return {"restored": restored, "preserved_current": preserved, "errors": errors, "status": status}

    def file_history(self, path: str) -> list[dict]:
        """Em quais versões de backup um arquivo aparece (e se o conteúdo mudou)."""
        wanted = str(Path(path).expanduser())
        out = []
        for job in self.jobs:
            for v in self.versions(job["id"]):
                for f in self.store.read(v["manifest"], {"files": []})["files"]:
                    if f["path"] == wanted:
                        out.append({"job_id": job["id"], "job": job["name"], "version_id": v["id"],
                                    "timestamp": v["timestamp"], "sha256": f["sha256"], "bytes": f["bytes"],
                                    "entry": f"{f['root']}/{f['rel']}"})
        return out

    # ------------------------------------------------------------------
    # Abrir a pasta no gerenciador de arquivos do sistema
    # ------------------------------------------------------------------
    def open_folder(self, job_id: str = "") -> dict:
        folder = self.folder_for(self.job(job_id)) if job_id else self.store.root / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(folder))                       # type: ignore[attr-defined]  (Explorer)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            opener = shutil.which("xdg-open")
            if not opener:
                raise RuntimeError("xdg-open não encontrado; abra manualmente: " + str(folder))
            subprocess.Popen([opener, str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"opened": str(folder)}

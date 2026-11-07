"""Agendador interno: roda numa thread separada enquanto o serviço está aberto.

* Organização automática: por padrão a cada 60 minutos ("interval"), ou diária/semanal
  num horário, ou desligada.
* Backups: cada regra de backup tem seu próprio intervalo (interval_hours).
* Tarefas vencidas enquanto o PC estava desligado rodam assim que o serviço volta.
* Detecta alterações externas nas pastas monitoradas (tamanho/data mudaram sem ser
  pelo aplicativo) e registra medições de espaço ocupado.

Conceito de SO: threads (concorrência dentro do processo) e agendamento de tarefas.
O início automático do próprio serviço no login é feito pelo SO (cron/Agendador de
Tarefas/pasta Inicializar), configurado pelos scripts de instalação.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

from .backups import Backups
from .organizer import Organizer, friendly_error
from .reports import Reports
from .storage import Store, now

CHECK_EVERY_SECONDS = 15


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        value = datetime.fromisoformat(stamp)
        return value.astimezone().replace(tzinfo=None) if value.tzinfo else value
    except ValueError:
        return None


class Scheduler:
    def __init__(self, store: Store, organizer: Organizer, backups: Backups, reports: Reports):
        self.store, self.organizer, self.backups, self.reports = store, organizer, backups, reports
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.last_scan = 0.0
        self.last_error = ""

    # ------------------------------------------------------------------
    # Cálculo de horários
    # ------------------------------------------------------------------
    def next_organize(self) -> datetime | None:
        sched = self.store.config.get("organize_schedule", {})
        frequency = sched.get("frequency", "interval")
        current = datetime.now()
        last = _parse(self.store.config.get("last_runs", {}).get("organize"))
        if frequency == "off":
            return None
        if frequency == "interval":
            minutes = max(1, int(sched.get("interval_minutes", 60)))
            return (last + timedelta(minutes=minutes)) if last else current
        try:
            hour, minute = map(int, str(sched.get("time", "09:00")).split(":"))
        except ValueError:
            return None
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if frequency == "weekly":
            candidate -= timedelta(days=(candidate.weekday() - int(sched.get("weekday", 0))) % 7)
            step = timedelta(days=7)
        else:
            step = timedelta(days=1)
        # candidate agora é o último horário agendado <= hoje; se já rodou depois dele, vai para o próximo.
        if candidate > current:
            candidate -= step
        if last and last >= candidate:
            candidate += step
        return candidate

    def organize_due(self) -> bool:
        moment = self.next_organize()
        return moment is not None and moment <= datetime.now()

    def status(self) -> dict:
        nxt = self.next_organize()
        return {"running": bool(self.thread and self.thread.is_alive()),
                "next_organize": nxt.isoformat(timespec="minutes") if nxt else "",
                "last_organize": self.store.config.get("last_runs", {}).get("organize", ""),
                "check_every_seconds": CHECK_EVERY_SECONDS, "last_error": self.last_error,
                "backups": [{"id": j["id"], "name": j["name"], "next": self.backups.next_run(j)}
                            for j in self.store.config.get("backup_jobs", [])]}

    # ------------------------------------------------------------------
    # Alterações externas
    # ------------------------------------------------------------------
    def scan_changes(self) -> list[str]:
        """Compara tamanho+data atual com a varredura anterior."""
        old = self.store.read(self.store.snapshot_path, {})
        new, changed = {}, []
        for path in self.organizer.scan(recursive=True):
            try:
                st = path.stat()
            except OSError:
                continue
            fingerprint = f"{st.st_size}:{st.st_mtime_ns}"
            new[str(path)] = fingerprint
            if str(path) in old and old[str(path)] != fingerprint:
                changed.append(str(path))
        own = {e.get("destination") for e in self.store.history(limit=500)
               if e.get("operation") in ("move", "restore", "review") and e.get("status") == "ok"}
        for path in changed[:200]:
            if path not in own:
                self.store.event("external_change", "detected", source=path)
        self.store.write(self.store.snapshot_path, new)
        return changed

    # ------------------------------------------------------------------
    # Laço principal
    # ------------------------------------------------------------------
    def tick(self) -> None:
        """Uma verificação: organiza se venceu, roda backups vencidos, mede pastas."""
        if self.organize_due():
            try:
                self.organizer.organize(trigger="agendado")
            except RuntimeError:
                pass                                   # já há uma organização manual em andamento
        self.backups.run_due()
        if time.monotonic() - self.last_scan >= 3600 or not self.last_scan:
            self.last_scan = time.monotonic()
            self.scan_changes()
            self.reports.storage_snapshot()

    def loop(self) -> None:
        if self.store.config.get("organize_on_start"):
            try:
                self.organizer.organize(trigger="inicialização")
            except Exception as exc:
                self.store.event("organize", "error", trigger="inicialização", reason=friendly_error(exc))
        while not self.stop_event.is_set():
            try:
                self.tick()
                self.last_error = ""
            except Exception as exc:                  # o agendador nunca deve morrer
                self.last_error = f"{now()} {friendly_error(exc)}"
                self.store.event("scheduler", "error", reason=friendly_error(exc))
            self.stop_event.wait(CHECK_EVERY_SECONDS)

    def start(self) -> None:
        self.thread = threading.Thread(target=self.loop, name="Agendador-OrganizaLocal", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

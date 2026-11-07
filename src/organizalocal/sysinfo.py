"""Informações do sistema operacional exibidas na aba "Sistema".

Mostra, na prática, conceitos da disciplina:
  * Processo: PID, PPID, usuário, threads e memória (RSS) do próprio serviço.
  * Memória e CPU da máquina (Linux lê /proc; Windows usa a API do kernel via ctypes).
  * Armazenamento: espaço total/usado/livre dos discos das pastas monitoradas.
  * Variáveis de ambiente que o programa utiliza.
  * Permissões da pasta de dados.
"""
from __future__ import annotations

import getpass
import os
import platform
import shutil
import socket
import stat
import sys
import threading
import time
from pathlib import Path

from .storage import Store

STARTED = time.time()


def _linux_meminfo() -> dict:
    info = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            info[key] = int(value.strip().split()[0]) * 1024      # kB -> bytes
    except (OSError, ValueError):
        pass
    return info


def memory() -> dict:
    """Memória física total e disponível da máquina."""
    if os.name == "nt":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))   # type: ignore[attr-defined]
        return {"total": status.ullTotalPhys, "available": status.ullAvailPhys,
                "percent_used": status.dwMemoryLoad, "source": "kernel32.GlobalMemoryStatusEx"}
    info = _linux_meminfo()
    total, available = info.get("MemTotal", 0), info.get("MemAvailable", 0)
    return {"total": total, "available": available,
            "percent_used": round(100 * (1 - available / total), 1) if total else None,
            "source": "/proc/meminfo"}


def process_memory() -> int:
    """Memória residente (RSS) do processo atual em bytes."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()                  # type: ignore[attr-defined]
        ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)  # type: ignore
        return int(counters.WorkingSetSize)
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    except (ImportError, OSError):
        return 0


def cpu() -> dict:
    data = {"cores": os.cpu_count(), "model": platform.processor() or platform.machine()}
    if hasattr(os, "getloadavg"):
        try:
            data["load_average"] = [round(x, 2) for x in os.getloadavg()]   # 1, 5 e 15 minutos
        except OSError:
            pass
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                data["model"] = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return data


def disks(store: Store) -> list[dict]:
    """Espaço em disco de cada local relevante (sem repetir o mesmo disco)."""
    seen, out = set(), []
    places = [("Pasta de dados", store.root)] + [("Monitorada", Path(p)) for p in store.config.get("watch_dirs", [])]
    places += [("Backup", Path(j["destination"])) for j in store.config.get("backup_jobs", []) if j.get("destination")]
    for label, place in places:
        probe = place
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        try:
            usage = shutil.disk_usage(probe)
            device = probe.stat().st_dev
        except OSError:
            continue
        key = (device, usage.total)
        out.append({"label": label, "path": str(place), "total": usage.total, "used": usage.used,
                    "free": usage.free, "percent_used": round(100 * usage.used / usage.total, 1) if usage.total else 0,
                    "same_disk_as_previous": key in seen})
        seen.add(key)
    return out


def environment() -> dict:
    """Variáveis de ambiente relevantes (sem valores sensíveis)."""
    names = ["HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME",
             "ORGANIZALOCAL_DATA", "ORGANIZALOCAL_PORT", "PATH", "LANG", "SHELL", "COMSPEC", "TEMP", "TMPDIR"]
    env = {}
    for name in names:
        value = os.environ.get(name)
        if value is not None:
            env[name] = value if name != "PATH" else f"{len(value.split(os.pathsep))} diretórios"
    return env


def collect(store: Store, scheduler=None) -> dict:
    """Junta tudo em um dicionário para a API."""
    try:
        mode = stat.filemode(store.root.stat().st_mode)
    except OSError:
        mode = "?"
    return {
        "system": {"os": platform.system(), "release": platform.release(), "version": platform.version(),
                   "machine": platform.machine(), "hostname": socket.gethostname(),
                   "python": sys.version.split()[0], "executable": sys.executable},
        "process": {"pid": os.getpid(), "ppid": os.getppid() if hasattr(os, "getppid") else None,
                    "user": getpass.getuser(), "threads": [t.name for t in threading.enumerate()],
                    "rss_bytes": process_memory(), "uptime_seconds": int(time.time() - STARTED),
                    "cwd": os.getcwd()},
        "cpu": cpu(),
        "memory": memory(),
        "disks": disks(store),
        "environment": environment(),
        "data_dir": {"path": str(store.root), "permissions": mode,
                     "owner_only": mode.endswith("------") if os.name != "nt" else "ACL do Windows (perfil do usuário)"},
        "scheduler": scheduler.status() if scheduler else {},
    }

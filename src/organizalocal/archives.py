"""Inspeção e extração segura de arquivos compactados.

* ZIP e TAR: listagem e extração com a biblioteca padrão, bloqueando caminhos que
  escapam da pasta (path traversal "../"), links simbólicos, executáveis e
  "bombas" (limite de quantidade e de tamanho total).
* RAR e 7Z: somente listagem, executando o programa 7-Zip (7z/7zz/7za) ou unrar
  instalado no sistema — demonstra a execução de comandos do SO via subprocess.
Nada dentro dos pacotes é executado.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path

from . import rules as R
from .organizer import Organizer, under

TAR_EXT = (".tar", ".tgz", ".tar.gz", ".tar.bz2", ".tar.xz")
MAX_ENTRIES = 5000
MAX_EXTRACT_FILES = 3000
MAX_EXTRACT_BYTES = 2 * 1024 ** 3     # 2 GiB


def find_7zip() -> str | None:
    """Procura o executável do 7-Zip no PATH e nas pastas padrão do Windows."""
    for name in ("7z", "7zz", "7za"):
        found = shutil.which(name)
        if found:
            return found
    if os.name == "nt":
        for env in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env)
            if base and (Path(base) / "7-Zip" / "7z.exe").is_file():
                return str(Path(base) / "7-Zip" / "7z.exe")
    return None


def _list_with_7zip(path: Path) -> list[dict]:
    exe = find_7zip()
    if not exe:
        raise ValueError("Para inspecionar RAR/7Z instale o 7-Zip (Windows) ou p7zip/7zip (Linux: sudo apt install 7zip).")
    try:
        proc = subprocess.run([exe, "l", "-slt", "-sccUTF-8", "--", str(path)], capture_output=True,
                              stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                              timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Falha ou tempo excedido ao executar o 7-Zip.") from exc
    if proc.returncode != 0:
        raise ValueError("O 7-Zip não conseguiu listar o pacote (danificado ou protegido por senha).")
    _, separator, listing = proc.stdout.partition("----------")
    if not separator:
        raise ValueError("Saída do 7-Zip não reconhecida.")
    entries, current = [], {}
    for line in listing.splitlines() + [""]:
        line = line.strip()
        if not line:
            if "Path" in current and len(entries) < MAX_ENTRIES and current.get("Folder") != "+":
                try:
                    size = int(current.get("Size") or 0)
                except ValueError:
                    size = 0
                entries.append({"name": current["Path"], "bytes": size, "type": R.category(current["Path"])})
            current = {}
        elif " = " in line:
            key, value = line.split(" = ", 1)
            current[key] = value
    return entries


def _list_with_unrar(path: Path) -> list[dict]:
    exe = shutil.which("unrar")
    if not exe:
        return _list_with_7zip(path)
    proc = subprocess.run([exe, "lb", str(path)], capture_output=True, text=True, timeout=30, check=False)
    if proc.returncode != 0:
        raise ValueError("unrar não conseguiu listar o pacote.")
    return [{"name": n, "bytes": 0, "type": R.category(n)} for n in proc.stdout.splitlines()[:MAX_ENTRIES] if n]


def inspect(organizer: Organizer, path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.is_file() or organizer.excluded(p):
        raise ValueError("Arquivo indisponível ou protegido.")
    ext = R.extension(p)
    if ext == ".zip" or (R.detect_format(p) in ("zip", "office") and ext not in TAR_EXT):
        with zipfile.ZipFile(p) as archive:
            entries = [{"name": i.filename, "bytes": i.file_size, "type": R.category(i.filename)}
                       for i in archive.infolist() if not i.is_dir()][:MAX_ENTRIES]
        tool = "zipfile (Python)"
    elif ext in TAR_EXT:
        with tarfile.open(p, "r:*") as archive:
            entries = [{"name": m.name, "bytes": m.size, "type": R.category(m.name)}
                       for m in archive if m.isfile()][:MAX_ENTRIES]
        tool = "tarfile (Python)"
    elif ext == ".7z":
        entries, tool = _list_with_7zip(p), "7-Zip (programa do sistema)"
    elif ext == ".rar":
        entries, tool = _list_with_unrar(p), "unrar/7-Zip (programa do sistema)"
    else:
        raise ValueError("Formato não suportado (use ZIP, TAR, RAR ou 7Z).")
    risky = [e["name"] for e in entries if R.extension(e["name"]) in R.RISKY]
    organizer.store.event("archive_inspect", "ok", source=str(p), files=len(entries))
    return {"archive": str(p), "tool": tool, "count": len(entries), "entries": entries,
            "total_bytes": sum(e["bytes"] for e in entries), "risky": risky,
            "note": "Somente leitura: nada foi extraído nem executado."}


def extract(organizer: Organizer, path: str, directory: str) -> dict:
    source = Path(path).expanduser().resolve()
    dest = Path(directory).expanduser().resolve()
    if organizer.protected(dest, is_dir=True) or not organizer.can_write_dir(dest):
        raise PermissionError("Pasta de destino não permitida.")
    ext = R.extension(source)
    if ext != ".zip" and ext not in TAR_EXT:
        raise ValueError("Extração segura disponível para ZIP e TAR; RAR/7Z apenas inspeção.")
    dest.mkdir(parents=True, exist_ok=True)
    counters = {"files": 0, "bytes": 0}

    def output_for(name: str, size: int) -> Path:
        counters["files"] += 1
        counters["bytes"] += size
        if counters["files"] > MAX_EXTRACT_FILES or counters["bytes"] > MAX_EXTRACT_BYTES:
            raise ValueError("Limite de extração atingido (possível 'bomba' de compactação).")
        out = (dest / name).resolve()
        if not under(out, dest):
            raise ValueError(f"Caminho perigoso dentro do pacote: {name}")
        if out.exists():
            raise FileExistsError(f"A extração não substitui arquivos: {out}")
        if R.extension(out) in R.RISKY:
            raise ValueError(f"O pacote contém executável ({name}); extraia manualmente se confiar na origem.")
        out.parent.mkdir(parents=True, exist_ok=True)
        return out

    if ext == ".zip":
        with zipfile.ZipFile(source) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                if stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError("Links simbólicos não são extraídos.")
                out = output_for(item.filename, item.file_size)
                with archive.open(item) as a, open(out, "xb") as b:
                    shutil.copyfileobj(a, b)
    else:
        with tarfile.open(source, "r:*") as archive:
            for item in archive:
                if item.isdir():
                    continue
                if not item.isfile():
                    raise ValueError("O TAR contém links ou arquivos especiais (não permitido).")
                out = output_for(item.name, item.size)
                stream = archive.extractfile(item)
                if stream:
                    with stream as a, open(out, "xb") as b:
                        shutil.copyfileobj(a, b)
    organizer.store.event("extract", "ok", source=str(source), destination=str(dest), files=counters["files"])
    return {"extracted": counters["files"], "bytes": counters["bytes"], "directory": str(dest)}

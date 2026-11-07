"""Regras de organização: condições, prioridade, exceções e conflitos.

Atende HU01–HU05 e HU09 / RF01–RF06, RF10 e RF11.

Uma regra é um dicionário salvo no config.json:

    {
      "id": "a1b2c3", "name": "Documentos PDF", "enabled": true, "priority": 7,
      "conditions": {                 # todas as condições preenchidas precisam valer (E)
          "extensions": [".pdf"],      # HU01 — sem diferenciar maiúsculas
          "keywords": ["faculdade"],   # HU02 — qualquer palavra em qualquer posição do nome
          "categories": [], "formats": [], "prefix": "", "suffix": "", "glob": "",
          "regex": "", "size_min": null, "size_max": null,
          "modified_after": "", "modified_before": "", "age_days_min": null, "age_days_max": null
      },
      "destination": "C:/Users/kayky/Documents/PDFs",   # RF03
      "create_destination": true, "rename_pattern": "", "project_id": "",
      "exceptions": [                 # HU05 — verificadas antes de aplicar a regra
          {"id": "...", "conditions": {"keywords": ["boleto"]}, "action": "skip"},
          {"id": "...", "conditions": {"extensions": [".tmp"]}, "action": "move",
           "destination": "D:/Outro"}
      ]
    }
"""
from __future__ import annotations

import fnmatch
import re
import secrets
import time
from datetime import datetime
from pathlib import Path

# Categorias prontas (o usuário pode criar outras em config["categories"]).
CATEGORIES = {
    "Documentos": [".pdf", ".doc", ".docx", ".txt", ".odt", ".rtf", ".md", ".epub"],
    "Planilhas": [".xls", ".xlsx", ".ods", ".csv"],
    "Apresentações": [".ppt", ".pptx", ".odp", ".key"],
    "Imagens": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic", ".ico"],
    "Vídeos": [".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv"],
    "Músicas": [".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"],
    "Compactados": [".zip", ".rar", ".7z", ".tar", ".tgz", ".gz", ".tar.gz", ".tar.bz2", ".tar.xz"],
    "Código": [".py", ".c", ".cpp", ".h", ".hpp", ".js", ".ts", ".html", ".css", ".json", ".java", ".sql"],
    "Instaladores": [".exe", ".msi", ".deb", ".rpm", ".appimage", ".apk", ".dmg"],
}
# Extensões consideradas de risco (podem executar código).
RISKY = {".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".jar", ".scr", ".com",
         ".pif", ".sh", ".appimage", ".deb", ".rpm", ".apk", ".lnk", ".hta"}
# Extensões de arquivos temporários/incompletos (download em andamento, Office aberto...).
TEMP_SUFFIX = {".part", ".crdownload", ".download", ".tmp", ".temp", ".swp", ".lock", ".partial"}

# Assinaturas ("magic numbers") — os primeiros bytes revelam o formato REAL do arquivo,
# mesmo que a extensão esteja errada ou tenha sido trocada de propósito.
SIGNATURES = [
    (b"%PDF", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"), (b"GIF89a", "gif"),
    (b"PK\x03\x04", "zip"), (b"PK\x05\x06", "zip"),
    (b"Rar!\x1a\x07", "rar"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"\x1f\x8b", "gzip"),
    (b"BZh", "bzip2"),
    (b"\xfd7zXZ\x00", "xz"),
    (b"MZ", "executavel-windows"),
    (b"\x7fELF", "executavel-linux"),
    (b"ID3", "mp3"),
    (b"OggS", "ogg"),
    (b"fLaC", "flac"),
    (b"RIFF", "riff"),            # WAV/AVI/WEBP — refinado abaixo
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "office-antigo"),  # .doc/.xls/.ppt
    (b"{\\rtf", "rtf"),
    (b"\x1a\x45\xdf\xa3", "matroska"),
]
# Formato real -> extensões coerentes (usado para detectar disfarces, ex.: "foto.jpg" que é .exe).
FORMAT_EXTENSIONS = {
    "pdf": {".pdf"}, "png": {".png"}, "jpeg": {".jpg", ".jpeg", ".jfif"}, "gif": {".gif"},
    "executavel-windows": {".exe", ".dll", ".msi", ".scr", ".com", ".sys"},
    "executavel-linux": {"", ".so", ".bin", ".run", ".appimage", ".elf"},
}
FORMAT_LABELS = {
    "pdf": "PDF", "png": "Imagem PNG", "jpeg": "Imagem JPEG", "gif": "Imagem GIF",
    "zip": "Pacote ZIP", "office": "Documento Office (docx/xlsx/pptx)", "rar": "Pacote RAR",
    "7z": "Pacote 7Z", "gzip": "GZIP", "bzip2": "BZIP2", "xz": "XZ",
    "executavel-windows": "Executável Windows", "executavel-linux": "Executável Linux",
    "mp3": "Áudio MP3", "ogg": "Áudio OGG", "flac": "Áudio FLAC", "wav": "Áudio WAV",
    "avi": "Vídeo AVI", "webp": "Imagem WEBP", "mp4": "Vídeo MP4/MOV", "matroska": "Vídeo MKV/WEBM",
    "office-antigo": "Office antigo (doc/xls/ppt)", "rtf": "RTF", "texto": "Texto", "binario": "Binário",
}


def extension(path) -> str:
    """Extensão em minúsculas, reconhecendo extensões duplas como .tar.gz (RNF: sem caixa)."""
    name = Path(path).name.lower()
    for double in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if name.endswith(double):
            return double
    return Path(name).suffix


def category(path, custom: dict | None = None) -> str:
    """Categoria da extensão; categorias personalizadas têm preferência."""
    ext = extension(path)
    for label, extensions in (custom or {}).items():
        if ext in [str(e).lower() for e in extensions]:
            return label
    for label, extensions in CATEGORIES.items():
        if ext in extensions:
            return label
    return "Outros"


def detect_format(path) -> str:
    """Lê os primeiros bytes do arquivo para descobrir o formato real."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(512)
    except OSError:
        return "desconhecido"
    if not head:
        return "texto"
    for signature, label in SIGNATURES:
        if head.startswith(signature):
            if label == "zip" and (b"[Content_Types].xml" in head or b"word/" in head
                                   or b"xl/" in head or b"ppt/" in head):
                return "office"
            if label == "riff":
                kind = head[8:12]
                return {b"WAVE": "wav", b"AVI ": "avi", b"WEBP": "webp"}.get(kind, "binario")
            return label
    if head[4:8] == b"ftyp":                 # contêiner MP4/MOV
        return "mp4"
    try:
        head.decode("utf-8")
        return "texto"
    except UnicodeDecodeError:
        return "binario"


def is_disguised(path) -> bool:
    """True quando o conteúdo é executável, mas a extensão finge ser outra coisa."""
    real = detect_format(path)
    if real not in ("executavel-windows", "executavel-linux"):
        return False
    return extension(path) not in FORMAT_EXTENSIONS[real]


def clean_name(filename: str) -> str:
    """Remove caracteres proibidos no Windows/Linux e nomes reservados (CON, PRN...)."""
    p = Path(filename)
    suffix = "".join(p.suffixes[-2:]) if extension(p) in (".tar.gz", ".tar.bz2", ".tar.xz") else p.suffix
    base = p.name[: -len(suffix)] if suffix else p.name
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip(" .")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if base.upper() in reserved:
        base += "_"
    return (base[: max(1, 180 - len(suffix))] or "arquivo") + suffix


def render_name(path, pattern: str, sequence: int = 1) -> str:
    """Aplica um modelo de nome: {name} {ext} {date} {year} {month} {day} {timestamp} {seq}."""
    p = Path(path)
    if not pattern:
        return clean_name(p.name)
    stamp = datetime.fromtimestamp(p.stat().st_mtime)
    values = {"name": p.stem, "ext": p.suffix.lstrip("."), "date": stamp.strftime("%Y-%m-%d"),
              "year": stamp.strftime("%Y"), "month": stamp.strftime("%m"), "day": stamp.strftime("%d"),
              "timestamp": stamp.strftime("%Y%m%d_%H%M%S"), "seq": str(sequence).zfill(3)}
    try:
        rendered = pattern.format_map(values)
    except (KeyError, ValueError, IndexError) as exc:
        raise ValueError("Modelo de nome inválido; use {name}, {ext}, {date}, {year}, {month}, "
                         "{day}, {timestamp} ou {seq}.") from exc
    if p.suffix and not rendered.lower().endswith(p.suffix.lower()):
        rendered += p.suffix
    return clean_name(rendered)


def _as_list(value) -> list[str]:
    """Aceita lista ou texto separado por vírgulas."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        value = value.split(",")
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_extension(value: str) -> str:
    value = str(value).strip().lower()
    return value if value.startswith(".") else "." + value


def has_conditions(conditions: dict) -> bool:
    return any(v not in (None, "", [], {}) for v in (conditions or {}).values())


def matches(path, conditions: dict, custom_categories: dict | None = None) -> bool:
    """Avalia TODAS as condições preenchidas (combinação E). Sem condições = False."""
    conditions = conditions or {}
    if not has_conditions(conditions):
        return False
    path = Path(path)
    name = path.name.casefold()

    # HU01 — extensão (uma ou várias, sem diferenciar maiúsculas)
    extensions = [normalize_extension(e) for e in _as_list(conditions.get("extensions"))]
    if extensions and extension(path) not in extensions:
        return False
    # Categoria (Documentos, Imagens...)
    categories = _as_list(conditions.get("categories"))
    if categories and category(path, custom_categories) not in categories:
        return False
    # HU02 — palavra/expressão em qualquer posição do nome (basta uma da lista)
    keywords = [k.casefold() for k in _as_list(conditions.get("keywords") or conditions.get("contains"))]
    if keywords and not any(k in name for k in keywords):
        return False
    if conditions.get("prefix") and not name.startswith(str(conditions["prefix"]).casefold()):
        return False
    if conditions.get("suffix"):
        stem = path.stem.casefold()
        wanted = str(conditions["suffix"]).casefold()
        if not (stem.endswith(wanted) or name.endswith(wanted)):
            return False
    if conditions.get("glob") and not fnmatch.fnmatch(name, str(conditions["glob"]).casefold()):
        return False
    if conditions.get("regex"):
        try:
            if not re.search(conditions["regex"], path.name, re.IGNORECASE):
                return False
        except re.error:
            return False
    # Formato real do conteúdo (lê os bytes iniciais do arquivo)
    formats = _as_list(conditions.get("formats"))
    if formats and detect_format(path) not in formats:
        return False

    # Condições que dependem de metadados do sistema de arquivos (stat)
    size_keys = ("size_min", "size_max", "modified_after", "modified_before",
                 "age_days_min", "age_days_max", "created_after", "created_before")
    if any(conditions.get(k) not in (None, "") for k in size_keys):
        try:
            st = path.stat()
        except OSError:
            return False
        if conditions.get("size_min") not in (None, "") and st.st_size < int(conditions["size_min"]):
            return False
        if conditions.get("size_max") not in (None, "") and st.st_size > int(conditions["size_max"]):
            return False
        # Observação: no Linux st_ctime é a última mudança de metadados, não a criação.
        for field, stamp in (("modified", st.st_mtime), ("created", st.st_ctime)):
            for side in ("after", "before"):
                raw = conditions.get(f"{field}_{side}")
                if raw:
                    try:
                        bound = datetime.fromisoformat(str(raw)).timestamp()
                    except ValueError:
                        return False
                    if (side == "after" and stamp < bound) or (side == "before" and stamp > bound):
                        return False
        age_days = (time.time() - st.st_mtime) / 86400
        if conditions.get("age_days_min") not in (None, "") and age_days < float(conditions["age_days_min"]):
            return False
        if conditions.get("age_days_max") not in (None, "") and age_days > float(conditions["age_days_max"]):
            return False
    return True


def normalize_rule(payload: dict) -> dict:
    """Limpa os campos vindos da interface antes de validar/salvar."""
    rule = dict(payload)
    conditions = dict(rule.get("conditions") or {})
    if "contains" in conditions and "keywords" not in conditions:
        conditions["keywords"] = conditions.pop("contains")
    for key in ("extensions", "keywords", "categories", "formats"):
        values = _as_list(conditions.get(key))
        conditions[key] = [normalize_extension(v) for v in values] if key == "extensions" else values
    for key in ("size_min", "size_max", "age_days_min", "age_days_max"):
        if conditions.get(key) in ("", None):
            conditions[key] = None
    rule["conditions"] = {k: v for k, v in conditions.items() if v not in (None, "", [])}
    rule["name"] = str(rule.get("name") or "Regra sem nome").strip()[:120]
    rule["priority"] = int(rule.get("priority", 5))
    rule["enabled"] = bool(rule.get("enabled", True))
    rule["create_destination"] = bool(rule.get("create_destination", True))
    rule["destination"] = str(rule.get("destination") or "").strip()
    rule.setdefault("rename_pattern", "")
    rule.setdefault("project_id", "")
    exceptions = []
    for item in rule.get("exceptions") or []:
        exc = dict(item)
        exc["id"] = exc.get("id") or secrets.token_hex(4)
        exc["conditions"] = normalize_rule({"conditions": exc.get("conditions", {})})["conditions"]
        exc["action"] = exc.get("action") or ("move" if exc.get("destination") else "skip")
        exc["destination"] = str(exc.get("destination") or "").strip()
        exc["description"] = str(exc.get("description") or "")[:200]
        exceptions.append(exc)
    rule["exceptions"] = exceptions
    return rule


def validate_rule(rule: dict, *, is_protected=None, can_write=None) -> list[str]:
    """Retorna a lista de problemas da regra (vazia = válida)."""
    errors = []
    conditions = rule.get("conditions") or {}
    if not has_conditions(conditions):
        errors.append("Defina pelo menos uma condição (extensão, palavra no nome, categoria...).")
    if not rule.get("destination") and not rule.get("project_id"):
        errors.append("Informe a pasta de destino.")
    if not 0 <= int(rule.get("priority", 0)) <= 10:
        errors.append("A prioridade deve estar entre 0 e 10.")
    for ext in conditions.get("extensions", []):
        if not re.fullmatch(r"\.[a-z0-9][a-z0-9.]{0,14}", ext):
            errors.append(f"Extensão inválida: {ext}")
    if conditions.get("regex"):
        try:
            re.compile(conditions["regex"])
        except re.error:
            errors.append("Expressão regular inválida.")
    for key in ("size_min", "size_max"):
        if conditions.get(key) is not None:
            try:
                if int(conditions[key]) < 0:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(f"{key} precisa ser um número de bytes >= 0.")
    for key in ("modified_after", "modified_before", "created_after", "created_before"):
        if conditions.get(key):
            try:
                datetime.fromisoformat(str(conditions[key]))
            except ValueError:
                errors.append(f"Data inválida em {key} (use AAAA-MM-DD).")
    if rule.get("rename_pattern"):
        try:
            rule["rename_pattern"].format_map({k: "x" for k in
                                               ("name", "ext", "date", "year", "month", "day", "timestamp", "seq")})
        except (KeyError, ValueError, IndexError):
            errors.append("Modelo de nome inválido.")
    destination = rule.get("destination")
    if destination:
        dest = Path(destination).expanduser()
        if not dest.is_absolute():
            errors.append("O destino deve ser um caminho completo (ex.: C:\\Users\\voce\\Documents\\PDFs).")
        elif is_protected and is_protected(dest):
            errors.append("O destino está dentro de uma área protegida (pasta de dados do aplicativo).")
        elif not dest.exists() and not rule.get("create_destination"):
            errors.append("A pasta de destino não existe e a criação automática está desligada.")
        elif can_write and not can_write(dest):
            errors.append("Sem permissão de escrita na pasta de destino (RNF03).")
    for exc in rule.get("exceptions", []):
        if not has_conditions(exc.get("conditions", {})):
            errors.append("Exceção sem condição.")
        if exc.get("action") == "move" and not exc.get("destination"):
            errors.append("Exceção do tipo 'mover para outra pasta' precisa de destino.")
    return errors


def evaluate(path, rules: list[dict], custom_categories: dict | None = None, only_rule: str | None = None) -> dict:
    """Decide qual regra vale para o arquivo (HU03 / RF11).

    Retorna:
      matched   -> todas as regras ativas cujas condições batem (ordem de prioridade)
      rule      -> a regra vencedora (ou None)
      conflict  -> True se mais de uma regra bateu (resolvido pela prioridade)
      tie       -> True se as regras de maior prioridade empataram (conflito NÃO resolvido)
      exception -> exceção que se aplicou à regra vencedora (ou None)
    """
    candidates = [r for r in rules
                  if r.get("enabled", True)                      # HU09: desativadas não participam
                  and (not only_rule or r.get("id") == only_rule)
                  and matches(path, r.get("conditions", {}), custom_categories)]
    candidates.sort(key=lambda r: int(r.get("priority", 0)), reverse=True)
    result = {"matched": candidates, "rule": None, "conflict": len(candidates) > 1,
              "tie": False, "exception": None}
    if not candidates:
        return result
    top = int(candidates[0].get("priority", 0))
    best = [r for r in candidates if int(r.get("priority", 0)) == top]
    if len(best) > 1:
        result["tie"] = True                                       # empate: vai para revisão
        return result
    winner = best[0]
    result["rule"] = winner
    # HU05: exceções são verificadas ANTES de aplicar a regra.
    for exc in winner.get("exceptions", []):
        if matches(path, exc.get("conditions", {}), custom_categories):
            result["exception"] = exc
            break
    return result


def overlapping_rules(rules: list[dict]) -> list[dict]:
    """Detecta antecipadamente pares de regras ativas que podem empatar (mesma prioridade
    e extensões/categorias/palavras em comum)."""
    problems = []
    active = [r for r in rules if r.get("enabled", True)]
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if int(a.get("priority", 0)) != int(b.get("priority", 0)):
                continue
            ca, cb = a.get("conditions", {}), b.get("conditions", {})
            shared = []
            for key in ("extensions", "categories", "keywords", "formats"):
                common = set(ca.get(key, [])) & set(cb.get(key, []))
                if common:
                    shared.append(f"{key}: {', '.join(sorted(common))}")
            only_one_side = any((k in ca) != (k in cb) for k in ("extensions", "keywords"))
            if shared or ca == cb or only_one_side:
                problems.append({"rules": [a.get("name"), b.get("name")], "priority": a.get("priority"),
                                 "detail": "; ".join(shared) or "condições podem coincidir"})
    return problems


def example_rules(home: Path) -> list[dict]:
    """Regras de exemplo criadas DESATIVADAS na primeira execução (o usuário revisa e ativa)."""
    docs = home / "Documents"
    base = [
        ("Documentos PDF", {"extensions": [".pdf"]}, docs / "PDFs", 5),
        ("Office (Word, Excel, PowerPoint)", {"extensions": [".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt"]},
         docs / "Office", 5),
        ("Imagens", {"categories": ["Imagens"]}, home / "Pictures" / "Downloads", 4),
        ("Arquivos da faculdade", {"keywords": ["faculdade", "fatec", "trabalho", "atividade"]},
         docs / "Faculdade", 8),
        ("Compactados", {"categories": ["Compactados"]}, home / "Downloads" / "Compactados", 3),
    ]
    rules = []
    for name, conditions, destination, priority in base:
        rules.append(normalize_rule({"id": secrets.token_hex(6), "name": name, "conditions": conditions,
                                     "destination": str(destination), "priority": priority,
                                     "enabled": False, "create_destination": True}))
    # Exemplo de exceção (HU05): boletos não vão para a pasta de PDFs.
    rules[0]["exceptions"] = [{"id": secrets.token_hex(4), "conditions": {"keywords": ["boleto"]},
                               "action": "skip", "destination": "",
                               "description": "Boletos ficam em Downloads"}]
    return rules

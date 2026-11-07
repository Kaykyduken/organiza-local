"""Estatísticas, relatórios PDF, medições de armazenamento, limites e vencimentos.

O PDF é gerado "à mão" (formato PDF 1.4 com a fonte Helvetica embutida no leitor),
sem bibliotecas externas — assim o programa continua funcionando offline.
"""
from __future__ import annotations

import json
import textwrap
from datetime import date, datetime
from pathlib import Path

from . import rules as R
from .storage import Store, now

OPERATION_NAMES = {
    "move": "Movido", "quarantine": "Quarentena", "organize": "Organização", "backup": "Backup",
    "restore": "Restauração", "undo": "Desfeito", "review": "Revisão", "rename": "Renomeado",
    "rule_save": "Regra salva", "rule_delete": "Regra excluída", "rule_toggle": "Regra ativada/desativada",
    "rule_priority": "Prioridade alterada", "config_save": "Configuração", "external_change": "Alteração externa",
}


# ----------------------------------------------------------------------
# PDF mínimo
# ----------------------------------------------------------------------
def _pdf_escape(text: str) -> bytes:
    data = text.encode("cp1252", "replace")          # cp1252 = WinAnsi (acentos do português)
    return data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def write_pdf(path: Path, title: str, lines: list[str]) -> None:
    """Cria um PDF A4 com título e linhas de texto, paginando automaticamente."""
    width, height, margin, leading = 595, 842, 40, 12
    per_page = int((height - 2 * margin - 40) / leading)
    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(textwrap.wrap(line, 105, break_long_words=True, break_on_hyphens=False) or [""])
    pages = [wrapped[i:i + per_page] for i in range(0, len(wrapped), per_page)] or [[]]

    objects: list[bytes] = []
    # 1: catálogo, 2: árvore de páginas, 3: fonte normal, 4: fonte negrito
    kids = " ".join(f"{5 + i * 2} 0 R" for i in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    for number, page_lines in enumerate(pages, 1):
        stream = [b"BT", b"/F2 14 Tf", f"{margin} {height - margin} Td".encode(),
                  b"(" + _pdf_escape(title) + b") Tj",
                  b"/F1 8 Tf", f"0 -{leading * 2} Td".encode(), f"{leading} TL".encode()]
        for line in page_lines:
            stream.append(b"(" + _pdf_escape(line) + b") '")
        stream.append(b"ET")
        stream.append(b"BT /F1 8 Tf " + f"{width - margin - 60} {margin - 15} Td".encode() +
                      b" (" + _pdf_escape(f"Página {number}/{len(pages)}") + b") Tj ET")
        content = b"\n".join(stream)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
                       f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                       f"/Contents {6 + (number - 1) * 2} 0 R >>".encode())
        objects.append(f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


class Reports:
    def __init__(self, store: Store):
        self.store = store

    # ------------------------------------------------------------------
    # Estatísticas para o painel
    # ------------------------------------------------------------------
    def stats(self) -> dict:
        moves = errors = events = 0
        moved_bytes = 0
        by_ext: dict[str, int] = {}
        by_cat: dict[str, int] = {}
        by_day: dict[str, int] = {}
        by_rule: dict[str, int] = {}
        if self.store.history_path.exists():
            with self.store.lock, open(self.store.history_path, encoding="utf-8") as handle:
                for line in handle:
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    events += 1
                    if e.get("status") == "error":
                        errors += 1
                    if e.get("operation") in ("move", "review") and e.get("status") == "ok":
                        moves += 1
                        moved_bytes += int(e.get("bytes") or 0)
                        dest = e.get("destination", "")
                        ext = R.extension(dest) or "(sem extensão)"
                        cat = R.category(dest, self.store.config.get("categories"))
                        by_ext[ext] = by_ext.get(ext, 0) + 1
                        by_cat[cat] = by_cat.get(cat, 0) + 1
                        day = str(e.get("timestamp", ""))[:10]
                        by_day[day] = by_day.get(day, 0) + 1
                        rule = e.get("rule_name") or "Destino padrão"
                        by_rule[rule] = by_rule.get(rule, 0) + 1
        index = self.store.read(self.store.backup_index_path, {})
        return {"moves": moves, "moved_bytes": moved_bytes, "events": events, "errors": errors,
                "by_extension": dict(sorted(by_ext.items(), key=lambda x: -x[1])[:12]),
                "by_category": dict(sorted(by_cat.items(), key=lambda x: -x[1])),
                "by_rule": dict(sorted(by_rule.items(), key=lambda x: -x[1])[:12]),
                "by_day": dict(sorted(by_day.items())[-14:]),
                "backup_versions": sum(len(v) for v in index.values()),
                "backup_bytes": sum(int(x.get("stored_bytes", 0)) for v in index.values() for x in v),
                "pending_review": len(self.store.read(self.store.review_path, []))}

    # ------------------------------------------------------------------
    # Relatório diário em PDF
    # ------------------------------------------------------------------
    def daily_pdf(self, day: str = "") -> dict:
        day = day or date.today().isoformat()
        date.fromisoformat(day)                                 # valida o formato
        events = list(reversed(self.store.history({"date": day}, limit=20000)))
        lines = [f"Data: {day}   |   Operações registradas: {len(events)}   |   Gerado em {now()}", ""]
        for e in events:
            op = OPERATION_NAMES.get(e.get("operation"), e.get("operation"))
            lines.append(f"{e.get('timestamp', '')[11:19]}  {op}  [{e.get('status')}]  "
                         f"{e.get('rule_name') or e.get('detail') or ''}")
            if e.get("source"):
                lines.append(f"     Origem:  {e['source']}")
            if e.get("destination"):
                lines.append(f"     Destino: {e['destination']}")
            if e.get("reason"):
                lines.append(f"     Motivo:  {e['reason']}")
        filename = f"relatorio_{day}.pdf"
        write_pdf(self.store.root / "reports" / filename, "OrganizaLocal - Relatório diário", lines)
        self.store.event("report", "ok", detail=filename, files=len(events))
        return {"filename": filename, "events": len(events), "path": str(self.store.root / "reports" / filename)}

    def export_simulation(self, simulation: dict) -> dict:
        name = datetime.now().strftime("simulacao_%Y%m%d_%H%M%S.json")
        self.store.write(self.store.root / "exports" / name, simulation)
        return {"filename": name, "path": str(self.store.root / "exports" / name)}

    # ------------------------------------------------------------------
    # Medições de armazenamento, limites e vencimentos
    # ------------------------------------------------------------------
    def folder_size(self, folder: Path, only_category: str = "") -> tuple[int, int]:
        total = count = 0
        for p in folder.rglob("*"):
            try:
                if p.is_file() and not p.is_symlink() and \
                        (not only_category or R.category(p, self.store.config.get("categories")) == only_category):
                    total += p.stat().st_size
                    count += 1
            except OSError:
                continue
        return total, count

    def storage_snapshot(self) -> list[dict]:
        rows = []
        for folder in self.store.config.get("watch_dirs", []):
            path = Path(folder)
            if path.is_dir():
                size, count = self.folder_size(path)
                rows.append({"directory": folder, "bytes": size, "files": count, "timestamp": now()})
        history = self.store.read(self.store.storage_path, [])
        history.extend(rows)
        self.store.write(self.store.storage_path, history[-5000:])
        return rows

    def storage_history(self) -> list[dict]:
        return self.store.read(self.store.storage_path, [])[-200:]

    def check_limits(self) -> list[dict]:
        alerts = []
        for item in self.store.config.get("limits", []):
            maximum = int(item.get("max_bytes") or 0)
            if maximum <= 0:
                continue
            folders = [Path(item["path"])] if item.get("path") else \
                [Path(f) for f in self.store.config.get("watch_dirs", [])]
            total = sum(self.folder_size(f, item.get("category", ""))[0] for f in folders if f.is_dir())
            if total >= maximum * 0.9:
                alerts.append({"path": item.get("path", ""), "category": item.get("category", ""),
                               "bytes": total, "max_bytes": maximum,
                               "severity": "excedido" if total >= maximum else "próximo do limite"})
        return alerts

    def due_documents(self, days: int = 30) -> list[dict]:
        out = []
        for item in self.store.config.get("due_dates", []):
            try:
                remaining = (date.fromisoformat(item["due"]) - date.today()).days
            except (KeyError, ValueError):
                continue
            if remaining <= days:
                out.append({**item, "days_remaining": remaining})
        return sorted(out, key=lambda x: x["days_remaining"])

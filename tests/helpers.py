"""Utilitários compartilhados pelos testes.

Cada teste roda numa pasta temporária isolada: HOME/USERPROFILE e ORGANIZALOCAL_DATA
apontam para ela, então nada no computador real é tocado.
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Permite rodar com "python -m unittest" sem instalar o pacote.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from organizalocal.server import App  # noqa: E402


def make_file(path: Path, content: bytes | str = b"conteudo", age_seconds: int = 3600) -> Path:
    """Cria um arquivo com data de modificação no passado (para não parecer download em andamento)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode() if isinstance(content, str) else content)
    old = time.time() - age_seconds
    os.utime(path, (old, old))
    return path


class TempEnv(unittest.TestCase):
    """Base: cria HOME temporária com Downloads e um App sem agendador."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.downloads = self.home / "Downloads"
        self.downloads.mkdir(parents=True)
        self._env = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE", "ORGANIZALOCAL_DATA", "XDG_DATA_HOME")}
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.home)
        os.environ["ORGANIZALOCAL_DATA"] = str(self.root / "data")
        os.environ.pop("XDG_DATA_HOME", None)
        self.app = App(start_scheduler=False)
        self.app.store.config["rules"] = []          # começa sem as regras de exemplo
        self.app.store.save_config(snapshot=False)
        self.org = self.app.organizer

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def rule(self, name, conditions, dest_name, priority=5, **extra):
        """Cria uma regra ativa com destino em HOME/<dest_name>."""
        payload = {"name": name, "conditions": conditions, "destination": str(self.home / dest_name),
                   "priority": priority, "enabled": True, "create_destination": True, **extra}
        return self.org.save_rule(payload)

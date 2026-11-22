"""Diálogos de escolha no Windows, também disponíveis no Python embutido."""
import base64
import os
from pathlib import Path
import subprocess
import threading


_OPEN = threading.Lock()
_DIALOG = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Windows.Forms
$owner = [System.Windows.Forms.Form]::new()
$owner.TopMost = $true
try {
    if ($kind -eq 'folder') {
        $dialog = [System.Windows.Forms.FolderBrowserDialog]::new()
        $dialog.Description = 'OrganizaLocal - Escolha uma pasta'
        $dialog.ShowNewFolderButton = $true
        if ($dialog.ShowDialog($owner) -eq 'OK') { [Console]::Write($dialog.SelectedPath) }
    } else {
        $dialog = [System.Windows.Forms.OpenFileDialog]::new()
        $dialog.Title = 'OrganizaLocal - Escolha um arquivo'
        $dialog.CheckFileExists = $true
        if ($dialog.ShowDialog($owner) -eq 'OK') { [Console]::Write($dialog.FileName) }
    }
} finally {
    if ($dialog) { $dialog.Dispose() }
    $owner.Dispose()
}
"""


def select_path(kind: str) -> dict:
    if kind not in ("folder", "file"):
        raise ValueError("Escolha uma pasta ou um arquivo.")
    if os.name != "nt":
        raise RuntimeError("O seletor nativo está disponível no Windows. Informe o caminho completo.")
    if not _OPEN.acquire(blocking=False):
        raise RuntimeError("Já existe uma janela de seleção aberta.")
    try:
        command = base64.b64encode((f"$kind = '{kind}'\n" + _DIALOG).encode("utf-16-le")).decode("ascii")
        shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-STA", "-EncodedCommand", command],
                                capture_output=True, encoding="utf-8", errors="replace", timeout=180,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError("Não foi possível abrir o seletor. Informe o caminho completo.")
        return {"path": result.stdout.strip()}
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise RuntimeError("A seleção não foi concluída. Tente novamente ou informe o caminho.") from exc
    finally:
        _OPEN.release()

"""Comandos de terminal do OrganizaLocal.

    python -m organizalocal serve        # inicia o serviço (API + agendador) em primeiro plano
    python -m organizalocal open         # garante o serviço rodando e abre o site (atalho usa este)
    python -m organizalocal stop         # encerra o serviço de forma controlada
    python -m organizalocal status       # mostra PID, porta e próxima organização
    python -m organizalocal codigo       # mostra o código de pareamento
    python -m organizalocal organize [--simular] [--pasta P]
    python -m organizalocal backup [--job ID]
    python -m organizalocal relatorio [--dia AAAA-MM-DD]
    python -m organizalocal info         # informações do sistema operacional
    python -m organizalocal regras       # lista as regras por prioridade

Conceitos de SO: criação de processos filhos desacoplados do terminal (subprocess),
arquivo de PID, sinais (SIGTERM/SIGINT) para encerramento controlado e códigos de saída.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from . import APP_NAME, DEFAULT_PORT, VERSION


def port() -> int:
    return int(os.environ.get("ORGANIZALOCAL_PORT", DEFAULT_PORT))


def api(path: str, payload: dict | None = None, token: str = "", timeout: float = 5) -> dict:
    """Chama a API local do serviço que já está rodando."""
    data = json.dumps(payload or {}).encode() if payload is not None else None
    request = urllib.request.Request(f"http://127.0.0.1:{port()}{path}", data=data, method="POST" if data else "GET")
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def running() -> dict | None:
    try:
        return api("/api/ping", timeout=1.5)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def session() -> dict:
    from .storage import data_directory
    try:
        return json.loads((data_directory() / "state" / "session.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def action(command: str, payload: dict | None = None):
    """Executa uma ação pela API (quando o serviço está aberto)."""
    reply = api(f"/api/action/{command}", payload or {}, token=session().get("token", ""), timeout=600)
    return reply["result"]


# ----------------------------------------------------------------------
# serve / open / stop
# ----------------------------------------------------------------------
def cmd_serve(args) -> int:
    from .server import App, make_server
    if running():
        print("O OrganizaLocal já está em execução.")
        return 0
    app = App(port=args.port)
    if args.origin:
        os.environ["ORGANIZALOCAL_ALLOWED_ORIGIN"] = args.origin
    try:
        server = make_server(app, args.port)
    except OSError as exc:
        print(f"Não foi possível usar a porta {args.port}: {exc}")
        return 2
    info = app.security.start_session(args.port)
    app.store.pid_path.write_text(str(os.getpid()))          # arquivo de PID (state/server.pid)
    app.scheduler.start()
    app.store.event("service_start", "ok", detail=f"PID {os.getpid()} porta {args.port}")

    # Encerramento controlado ao receber SIGTERM (kill) ou SIGINT (Ctrl+C).
    def handle_signal(signum, _frame):
        app.store.event("service_signal", "ok", detail=f"sinal {signum}")
        import threading
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    print("=" * 60)
    print(f" {APP_NAME} {VERSION} — serviço local (somente 127.0.0.1)")
    print(f" PID: {os.getpid()}   Porta: {args.port}")
    print(f" Interface local: http://127.0.0.1:{args.port}")
    print(f" Código de pareamento: {info['code']} (válido por 30 min)")
    print(f" Dados: {app.store.root}")
    nxt = app.scheduler.status()["next_organize"]
    print(f" Próxima organização automática: {nxt or 'desligada'}")
    print(" Ctrl+C para encerrar.")
    print("=" * 60, flush=True)
    if not args.no_browser:
        open_browser(info["token"], app.store.config.get("site_url", ""), local=args.local)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        app.scheduler.stop()
        server.server_close()
        app.security.end_session()
        app.store.pid_path.unlink(missing_ok=True)
        app.store.event("service_stop", "ok", detail=f"PID {os.getpid()}")
        print("Serviço encerrado.")
    return 0


def spawn_background() -> None:
    """Inicia `serve` como processo separado, sem janela e sem depender do terminal."""
    from .storage import data_directory
    package_parent = str(Path(__file__).resolve().parent.parent)
    python = sys.executable
    if os.name == "nt":
        pythonw = Path(python).with_name("pythonw.exe")
        if pythonw.exists():
            python = str(pythonw)                              # sem janela de console
    env = dict(os.environ, PYTHONPATH=package_parent + os.pathsep + os.environ.get("PYTHONPATH", ""))
    log_dir = data_directory() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / "servico.log", "a", encoding="utf-8")
    command = [python, "-m", "organizalocal", "serve", "--no-browser", "--port", str(port())]
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200 | 0x08000000     # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
        subprocess.Popen(command, cwd=package_parent, env=env, stdout=log, stderr=log,
                         stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    else:
        subprocess.Popen(command, cwd=package_parent, env=env, stdout=log, stderr=log,
                         stdin=subprocess.DEVNULL, start_new_session=True, close_fds=True)


def site_reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=4):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def open_browser(token: str, site_url: str, local: bool = False) -> str:
    """Abre o site da Vercel (ou a interface local, se offline) já autenticado."""
    local_url = f"http://127.0.0.1:{port()}/"
    url = local_url
    if site_url and not local and site_reachable(site_url):
        url = site_url.rstrip("/") + "/"
    fragment = f"#token={token}&api=http://127.0.0.1:{port()}"
    webbrowser.open(url + fragment)
    return url


def cmd_open(args) -> int:
    if not running():
        print("Iniciando o serviço em segundo plano...")
        spawn_background()
        for _ in range(40):
            time.sleep(0.25)
            if running() and session().get("token"):
                break
        else:
            print("O serviço não respondeu. Veja o log em <pasta de dados>/logs/servico.log")
            return 1
    from .storage import Store
    site = Store().config.get("site_url", "")
    url = open_browser(session()["token"], site, local=args.local)
    print(f"Abrindo {url}")
    return 0


def cmd_stop(_args) -> int:
    if not running():
        print("O serviço não está em execução.")
        return 0
    try:
        action("shutdown")
        print("Pedido de encerramento enviado.")
    except Exception:
        pid = session().get("pid")
        if not pid:
            print("Não foi possível descobrir o PID do serviço.")
            return 1
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
        else:
            os.kill(int(pid), signal.SIGTERM)                  # encerramento controlado por sinal
        print(f"Sinal de encerramento enviado ao PID {pid}.")
    for _ in range(20):
        if not running():
            print("Serviço encerrado.")
            return 0
        time.sleep(0.25)
    return 1


def cmd_status(_args) -> int:
    ping = running()
    if not ping:
        print("Serviço PARADO.")
        return 3
    info = session()
    state = action("state")
    sched = state["scheduler"]
    print(f"Serviço RODANDO  PID {ping['pid']}  porta {port()}  versão {ping['version']}")
    print(f"Pastas monitoradas: {', '.join(state['config']['watch_dirs'])}")
    print(f"Regras ativas: {sum(1 for r in state['rules'] if r['enabled'])} de {len(state['rules'])}")
    print(f"Última organização: {sched['last_organize'] or 'nunca'} | próxima: {sched['next_organize'] or 'desligada'}")
    for b in sched["backups"]:
        print(f"Backup '{b['name']}': próxima execução {b['next'] or 'desativado'}")
    print(f"Iniciado em {info.get('started', '?')}")
    return 0


def cmd_code(_args) -> int:
    info = session()
    if not info:
        print("Serviço parado — inicie com `organizalocal open`.")
        return 3
    print(f"Código de pareamento: {info['code']}")
    return 0


# ----------------------------------------------------------------------
# Operações (usam a API se o serviço estiver aberto; senão rodam direto)
# ----------------------------------------------------------------------
def _local_app():
    from .server import App
    return App(start_scheduler=False)


def cmd_organize(args) -> int:
    payload = {"paths": args.pasta or None}
    command = "simulate" if args.simular else "organize"
    result = action(command, payload) if running() else (
        _local_app().organizer.simulate(args.pasta or None) if args.simular
        else _local_app().organizer.organize(args.pasta or None, trigger="terminal"))
    if args.simular:
        print(f"SIMULAÇÃO — nenhum arquivo foi movido. {result['count']} arquivos analisados.")
        for row in result["rows"]:
            if row["action"] in ("move", "default", "conflict", "quarantine", "tie", "exception"):
                print(f"  [{row['action']:>10}] {row['name']}  ->  {row['destination'] or row['reason']}")
        print(f"Seriam movidos: {result['would_move']}")
    else:
        print(f"Organização {result['status'].upper()}: {result['moved']} movidos, "
              f"{result['reviewed']} para revisão, {result['quarantined']} em quarentena, "
              f"{len(result['errors'])} falhas, {result['skipped']} ignorados.")
        for m in result["moves"]:
            print(f"  OK   {m['source']}  ->  {m['destination']}")
        for e in result["errors"]:
            print(f"  ERRO {e['file']}: {e['reason']}")
    return 0 if args.simular or not result["errors"] else 1


def cmd_backup(args) -> int:
    if running():
        jobs = action("state")["backup_jobs"]
        run = lambda job_id: action("backup_run", {"id": job_id})
    else:
        app = _local_app()
        jobs = app.store.config["backup_jobs"]
        run = app.backups.run
    selected = [j for j in jobs if not args.job or j["id"] == args.job or j["name"] == args.job]
    if not selected:
        print("Nenhuma regra de backup encontrada. Crie uma na aba Backups do site.")
        return 1
    status = 0
    for job in selected:
        try:
            result = run(job["id"])
            if result.get("created"):
                v = result["version"]
                print(f"Backup '{job['name']}': versão {v['id']} com {v['files']} arquivos -> {v['path']}")
                if result.get("removed_versions"):
                    print(f"  Retenção removeu: {', '.join(result['removed_versions'])}")
            else:
                print(f"Backup '{job['name']}': {result.get('reason')}")
        except Exception as exc:
            print(f"Backup '{job['name']}' FALHOU: {exc}")
            status = 1
    return status


def cmd_report(args) -> int:
    result = action("report", {"day": args.dia}) if running() else _local_app().reports.daily_pdf(args.dia)
    print(f"Relatório gerado: {result.get('path', result['filename'])} ({result['events']} eventos)")
    return 0


def cmd_info(_args) -> int:
    from . import sysinfo
    from .storage import Store
    data = action("sysinfo") if running() else sysinfo.collect(Store())
    gib = lambda b: f"{(b or 0) / 1024 ** 3:.1f} GiB"
    s, p, m = data["system"], data["process"], data["memory"]
    print(f"Sistema: {s['os']} {s['release']} ({s['machine']})  host {s['hostname']}  Python {s['python']}")
    print(f"Processo: PID {p['pid']}  PPID {p['ppid']}  usuário {p['user']}  RSS {(p['rss_bytes'] or 0) / 1024 ** 2:.1f} MiB")
    print(f"CPU: {data['cpu'].get('model')}  núcleos {data['cpu'].get('cores')}  carga {data['cpu'].get('load_average', '-')}")
    print(f"Memória: total {gib(m['total'])}  disponível {gib(m['available'])}  uso {m['percent_used']}%")
    for d in data["disks"]:
        print(f"Disco [{d['label']}] {d['path']}: livre {gib(d['free'])} de {gib(d['total'])} ({d['percent_used']}% usado)")
    print(f"Pasta de dados: {data['data_dir']['path']}  permissões {data['data_dir']['permissions']}")
    return 0


def cmd_rules(_args) -> int:
    rules = action("state")["rules"] if running() else _local_app().organizer.ordered_rules()
    for r in rules:
        state = "ATIVA " if r["enabled"] else "inativa"
        cond = ", ".join(f"{k}={v}" for k, v in r["conditions"].items())
        print(f"[{r['priority']:>2}] {state} {r['name']}: {cond} -> {r['destination']}"
              f"{'  (' + str(len(r['exceptions'])) + ' exceções)' if r['exceptions'] else ''}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="organizalocal", description=f"{APP_NAME} {VERSION}")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("serve", help="inicia o serviço local")
    p.add_argument("--port", type=int, default=port())
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--local", action="store_true", help="abre a interface local em vez da Vercel")
    p.add_argument("--origin", default="", help="origem extra autorizada (ex.: URL de preview da Vercel)")
    p = sub.add_parser("open", help="inicia (se preciso) e abre o site")
    p.add_argument("--local", action="store_true")
    sub.add_parser("stop", help="encerra o serviço")
    sub.add_parser("status", help="situação do serviço")
    sub.add_parser("codigo", help="mostra o código de pareamento")
    p = sub.add_parser("organize", help="organiza agora (ou simula)")
    p.add_argument("--simular", action="store_true")
    p.add_argument("--pasta", action="append")
    p = sub.add_parser("backup", help="executa regras de backup")
    p.add_argument("--job", default="")
    p = sub.add_parser("relatorio", help="gera o relatório PDF do dia")
    p.add_argument("--dia", default="")
    sub.add_parser("info", help="informações do sistema operacional")
    sub.add_parser("regras", help="lista as regras")
    args = parser.parse_args(argv)
    handlers = {"serve": cmd_serve, "open": cmd_open, "stop": cmd_stop, "status": cmd_status,
                "codigo": cmd_code, "organize": cmd_organize, "backup": cmd_backup,
                "relatorio": cmd_report, "info": cmd_info, "regras": cmd_rules}
    if not args.command:
        args = parser.parse_args(["open"])
    return handlers[args.command](args)

# Conceitos de Sistemas Operacionais no OrganizaLocal

Este guia ajuda cada integrante a explicar, na apresentação, **onde** e **como** cada conceito aparece no código.

## 1. Arquivos, diretórios e sistema de arquivos

**Onde:** `src/organizalocal/organizer.py` → `scan()`, `decide()` e `transfer()`.

- `os.walk(..., followlinks=False)` percorre as pastas sem seguir links simbólicos. Isso evita loops infinitos e evita mexer fora da pasta escolhida.
- `os.stat()` devolve os metadados: tamanho (`st_size`), data de modificação (`st_mtime`) e o **dispositivo** (`st_dev`).
- **Mover no mesmo disco**: `os.rename()` só troca a entrada do diretório, e o conteúdo não é copiado. É uma operação **atômica**: ou acontece inteira ou não acontece.
- **Mover para outro disco** não pode ser um simples rename. O programa:
  1. copia para um arquivo temporário (`tempfile.mkstemp`);
  2. confere o **SHA-256**;
  3. troca com `os.replace()`;
  4. confere de novo;
  5. só então apaga a origem.

  Se a origem estiver em uso (erro do Windows 32), a cópia é desfeita para não duplicar o arquivo.
- **Escrita atômica** da configuração (`storage.py → write()`): grava num temporário, chama `os.fsync()` para forçar a gravação no disco e troca com `os.replace()`. Uma queda de energia no meio não corrompe o `config.json`.
- **Formato real**: `rules.py → detect_format()` lê os primeiros 512 bytes (os "magic numbers": `%PDF`, `\x89PNG`, `MZ`, `\x7fELF`...). Assim o programa descobre que `foto.jpg` é na verdade um executável.

## 2. Permissões

- Antes de mover: `os.access(caminho, os.R_OK)` na origem e `os.W_OK` no destino (RNF03).
- Pasta de dados: `chmod 700` (`drwx------`), feito no `Store.__init__` e no `instalar.sh`.
- `state/session.json` (token de acesso): `chmod 600` (`-rw-------`). Só o dono lê.
- Scripts e lançador: `chmod 755` (executáveis).
- Os erros de permissão do SO (`EACCES`/`EPERM`) viram mensagens claras em `friendly_error()` (RNF09).

## 3. Processos

**Onde:** `src/organizalocal/cli.py`.

- `organizalocal open` verifica se o serviço responde em `/api/ping`. Se não responder, cria um **processo filho desacoplado**:
  - Linux: `subprocess.Popen(..., start_new_session=True)` — o processo ganha uma sessão própria e continua vivo quando o terminal fecha.
  - Windows: `pythonw.exe` com `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` — o processo roda sem janela.
- **Arquivo de PID**: `state/server.pid`.
- **Encerramento controlado**: `organizalocal stop` pede `shutdown` pela API. Como alternativa, envia **SIGTERM** (`os.kill`) no Linux ou `taskkill` no Windows. O serviço trata `SIGTERM`/`SIGINT` com `signal.signal`, para o agendador, apaga o PID e registra no histórico.
- A aba **Sistema** mostra PID, PPID, usuário dono do processo, memória residente (RSS), threads e tempo de execução.

## 4. Threads e concorrência

- O agendador roda em uma **thread** separada (`Agendador-OrganizaLocal`).
- O servidor HTTP é um `ThreadingHTTPServer`: cada requisição do site é atendida em uma thread.
- `threading.Lock` (`run_lock`) impede que uma organização manual e uma agendada rodem ao mesmo tempo.
- `threading.RLock` protege a escrita de arquivos JSON compartilhados.

## 5. Agendamento de tarefas

- **Interno** (`scheduler.py`): a cada 15 s verifica se a organização venceu. O padrão é **a cada 60 minutos**; também há diária, semanal ou desligada. Cada regra de backup tem seu próprio intervalo. Tarefas vencidas enquanto o PC estava desligado rodam quando o serviço volta.
- **Do sistema operacional** (início automático do serviço):
  - Linux: `crontab` com `@reboot` (feito pelo `instalar.sh`);
  - Windows: atalho na pasta **Inicializar** (`shell:startup`).
- **Alternativa clássica**: `scripts/agendar_cron.sh` coloca `0 * * * * organizalocal organize` e `30 2 * * * backup_agora.sh` no cron.

## 6. Memória, CPU e armazenamento

**Onde:** `src/organizalocal/sysinfo.py`.

- **Linux** lê os arquivos virtuais do kernel:
  - `/proc/meminfo`: memória total e disponível;
  - `/proc/self/status` (`VmRSS`): memória do processo;
  - `/proc/cpuinfo` e `os.getloadavg()`: CPU e carga média.
- **Windows** chama a API do kernel por `ctypes`:
  - `kernel32.GlobalMemoryStatusEx`: memória da máquina;
  - `psapi.GetProcessMemoryInfo`: memória do processo.
- **Disco**: `shutil.disk_usage()` mostra o espaço de cada pasta monitorada e de backup. Antes de criar um backup, o programa confere se há espaço livre suficiente.
- **Retenção**: manter no máximo N versões (padrão 5) é gerenciamento de armazenamento.

## 7. Variáveis de ambiente

| Variável | Uso |
|---|---|
| `APPDATA` (Windows) / `XDG_DATA_HOME` (Linux) | Pasta de dados do usuário |
| `HOME` / `USERPROFILE` | Pasta do usuário (descobrir Downloads) |
| `ORGANIZALOCAL_DATA` | Troca a pasta de dados (usada nos testes) |
| `ORGANIZALOCAL_PORT` | Troca a porta da API (padrão 8765) |
| `PATH` | O instalador do Windows adiciona a pasta do app ao PATH do usuário |
| `PYTHONPATH` | O processo filho recebe o caminho do pacote |

## 8. Execução de comandos do sistema

- `archives.py`: executa `7z l -slt` ou `unrar lb` para listar RAR e 7Z.
- `backups.py → open_folder()`: abre a pasta com `os.startfile` (Explorer) no Windows ou `xdg-open` no Linux.
- Os scripts Bash usam `uname`, `uptime`, `nproc`, `free`, `df`, `du`, `ps`, `pgrep`, `ls -l`, `crontab -l`, `curl`.

## 9. Registro de informações operacionais

- `history/events.jsonl`: uma linha JSON por evento. O arquivo só recebe acréscimos (*append-only*), e linhas antigas nunca são reescritas.
- Cada movimentação guarda origem, destino, regra, SHA-256, tamanho, método (`rename` ou `copy+sha256`) e id da execução.
- O relatório PDF é gerado sem bibliotecas externas (`reports.py → write_pdf`).
- O `scripts/verificar_sistema.sh` grava um relatório de verificação em texto.

## 10. Rede local (loopback) e segurança

- O servidor escuta **somente em `127.0.0.1`**: outro computador da rede não consegue acessar.
- A checagem do cabeçalho `Host` bloqueia ataques de *DNS rebinding*.
- **CORS**: só as origens autorizadas (o próprio `127.0.0.1` e a URL da Vercel configurada) recebem `Access-Control-Allow-Origin`.
- O cabeçalho `Access-Control-Allow-Private-Network: true` permite que um site HTTPS público chame o `localhost`, com a permissão do navegador.
- **Token aleatório** por sessão: o atalho passa o token no `#fragmento` da URL, que nunca chega ao servidor da Vercel. Como alternativa, há o pareamento por código de 6 dígitos, com limite de tentativas.

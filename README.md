# OrganizaLocal

**Organização automática de arquivos e backups versionados, rodando no seu computador.**

Projeto Integrador da disciplina de **Sistemas Operacionais** — Análise e Desenvolvimento de Sistemas, FATEC Itapetininga (2026).
Orientador: Prof. Me. Deivison S. Takatu.

| | |
|---|---|
| Painel (site) | https://organiza-local.vercel.app *(abre e controla o programa local)* |
| Versão | 1.0.0 |
| Sistemas | Windows 10/11 e Linux |
| Linguagem | Python 3.10+ (somente biblioteca padrão, funciona offline) |


![Painel do OrganizaLocal](docs/prints/d08_resultado.jpg)

---

## 1. Objetivo e problema

A pasta **Downloads** vira um depósito: PDFs da faculdade, boletos, instaladores, imagens e planilhas misturados. Organizar à mão toma tempo e quase ninguém faz backup dos arquivos importantes.

O **OrganizaLocal** é um serviço que roda em segundo plano e:

1. **organiza automaticamente**, de hora em hora (padrão), os arquivos de uma pasta escolhida (padrão: Downloads), movendo cada um para a pasta definida por **regras criadas pelo usuário** — por extensão, palavra no nome, categoria, formato real do conteúdo, tamanho ou data, com **prioridade** e **exceções**;
2. faz **backups periódicos por regras**, guardando até **N versões** (padrão **5**) e apagando as mais antigas automaticamente;
3. registra **tudo** num histórico local: o que foi movido, de onde, para onde, por qual regra e quando.

O painel de controle é um **site publicado na Vercel**. Ao clicar no atalho do programa, o site abre já conectado ao serviço local. **Nenhum arquivo sai do computador**: o site só envia comandos para `http://127.0.0.1:8765`. Sem internet, o atalho abre a mesma interface servida pelo próprio programa.

## 2. Integrantes

| Integrante | Responsabilidade principal |
|---|---|
| Kayky Gabriel Silvano Tomé | Arquitetura, motor de regras e integração com a Vercel |
| `<Integrante 2>` | `<ex.: backups e restauração>` |
| `<Integrante 3>` | `<ex.: scripts de instalação e automação>` |
| `<Integrante 4>` | `<ex.: interface web e testes>` |

> As contribuições de cada integrante podem ser conferidas no histórico de commits do GitHub (`git shortlog -sn`).

## 3. Tecnologias

- **Python 3.10+**, somente biblioteca padrão: `os`, `shutil`, `pathlib`, `hashlib`, `zipfile`, `tarfile`, `subprocess`, `threading`, `http.server`, `json`, `ctypes`. Não precisa de `pip install`.
- **HTML, CSS e JavaScript puro** na interface, publicada na **Vercel** como site estático.
- **Shell Script (Bash)** para instalar e automatizar no Linux, e **PowerShell/Batch** no Windows.
- **cron** (Linux) e a pasta **Inicializar** (Windows) para o início automático.
- **Git e GitHub** para o versionamento, e **unittest/pytest** para os testes.

## 4. Conceitos de Sistemas Operacionais aplicados

| Conceito | Onde aparece no projeto | Por que foi escolhido |
|---|---|---|
| **Manipulação de arquivos e diretórios** | `organizer.py`: `os.walk`, `os.stat`, `os.rename`, `shutil.copy2`, `mkdir` | É o coração do problema: ler, mover, copiar e criar pastas. |
| **Sistema de arquivos (mesmo disco × outro disco)** | `Organizer.transfer()`: no mesmo disco usa `os.rename`, uma troca atômica da entrada do diretório. Entre discos, copia, confere o SHA-256 e só então apaga a origem. | Mostra a diferença entre mover e copiar no nível do SO e garante integridade (RNF05). |
| **Permissões** | `os.access` antes de mover; pasta de dados com `chmod 700`; `session.json` com `chmod 600`; `chmod 755` no instalador | Evitar movimentações não autorizadas (RNF03) e proteger o token. |
| **Processos** | `cli.py`: o serviço roda como processo separado (`subprocess.Popen` com `start_new_session`/`DETACHED_PROCESS`), arquivo de PID, encerramento por sinal (`SIGTERM`) ou `taskkill`; a aba Sistema mostra PID, PPID, RSS e threads | Um organizador automático precisa rodar em segundo plano, independente do terminal. |
| **Threads e concorrência** | Agendador em thread própria; `ThreadingHTTPServer` com uma thread por requisição; `threading.Lock` impede duas organizações simultâneas | Fazer o agendamento e atender o site ao mesmo tempo. |
| **Agendamento de tarefas** | Organização de hora em hora e backups por intervalo (`scheduler.py`); `@reboot` no cron; `agendar_cron.sh` (`0 * * * *`); pasta Inicializar do Windows | É o requisito principal: organizar sozinho periodicamente. |
| **Memória, CPU e disco** | `sysinfo.py` lê `/proc/meminfo`, `/proc/self/status` e `os.getloadavg` no Linux, e `GlobalMemoryStatusEx`/`GetProcessMemoryInfo` via `ctypes` no Windows; `shutil.disk_usage` antes de cada backup | Monitorar os recursos e não lotar o disco com backups. |
| **Variáveis de ambiente** | `APPDATA`, `XDG_DATA_HOME`, `HOME`/`USERPROFILE`, `ORGANIZALOCAL_DATA`, `ORGANIZALOCAL_PORT`; o instalador do Windows altera o `PATH` do usuário | Achar a pasta certa de cada usuário em cada SO. |
| **Execução de comandos do SO** | 7-Zip/unrar via `subprocess`, `xdg-open`/`explorer` para abrir pastas, `crontab`, `df`, `free`, `ps` nos scripts | Integrar com ferramentas já existentes no sistema. |
| **Registro de informações operacionais** | `history/events.jsonl` (log só de acréscimo), relatórios PDF, `verificar_sistema.sh` | Rastreabilidade: o que aconteceu, quando e por quê. |
| **Rede local (loopback)** | Servidor ligado somente a `127.0.0.1`, com CORS e `Access-Control-Allow-Private-Network` | O site público fala com o programa local sem expor nada na rede. |

Mais detalhes em [`docs/conceitos-so.md`](docs/conceitos-so.md).

## 5. Funcionalidades

**Requisitos do grupo (HU01–HU12 / RF01–RF14):**

- Regras por **extensão** (HU01) e por **palavra no nome** (HU02), com pasta de destino (RF03).
- **Prioridade** de 0 a 10, com botões ▲/▼ e empate indicado e enviado para revisão (HU03, HU04, RF11).
- **Exceções** que impedem mover ou redirecionam para outra pasta, verificadas antes da regra (HU05).
- Consultar, editar, excluir com confirmação, ativar e desativar regras (HU06–HU09).
- **Simulação** que não move nada (HU10), **execução** com tratamento de conflitos (HU11) e **resultado** com falhas e motivos (HU12).

**Acrescentado ao pedido do grupo:**

- Organização automática **de hora em hora** (configurável: minutos, diária, semanal ou desligada).
- **Backups por regras**: origens, destino (inclusive HD externo), filtros, intervalo, **máximo de versões (padrão 5)**, ZIP ou cópia de pastas. Também é possível travar versões, restaurar (tudo ou um arquivo), comparar e verificar a integridade.
- **Formato real** do arquivo lido dos primeiros bytes: um executável disfarçado de `.jpg` vai para a revisão.
- **Instalador** que cria a pasta do aplicativo, o atalho e o início automático.

**Mantido da versão 0.9:**

- Categorias e projetos; glob, regex, tamanho e datas; renomear com modelo (`{date}_{name}`).
- Quarentena, caminhos protegidos e exclusões globais; perfis com PIN e senha para operações críticas.
- Fila de revisão e desfazer movimentações; duplicados por SHA-256; classificação sugerida; sandbox de regras.
- ZIP, TAR, RAR e 7Z: inspeção de todos; extração segura de ZIP e TAR.
- Relatório diário em PDF; limites de espaço; vencimentos de documentos; observações.
- Detecção de alterações externas; versões, importação e exportação da configuração.
- Temas claro, escuro e neon; pareamento por código.

## 6. Instalação e execução

### Instalador (recomendado)

Baixe em **https://organiza-local.vercel.app** (botões “Ainda não instalou?”) ou na pasta [`web/downloads/`](web/downloads):

| Sistema | Arquivo | Como instalar |
|---|---|---|
| **Windows 10/11** | `OrganizaLocal-Setup-1.0.0.exe` (9 MB, **Python já incluído**) | Dois cliques → Avançar → Instalar → Concluir. Não precisa de administrador. |
| **Linux** (Ubuntu, Debian, Mint, Pop!_OS) | `organizalocal_1.0.0_all.deb` | Dois cliques no arquivo, ou `sudo apt install ./organizalocal_1.0.0_all.deb` |

**Instalador do Windows:**

- Instala o programa e o Python 3.12 oficial em `%LOCALAPPDATA%\Programs\OrganizaLocal` e cria a pasta de dados `%APPDATA%\OrganizaLocal`.
- Cria os atalhos no Menu Iniciar e, opcionalmente, na Área de Trabalho.
- Opcionalmente, inicia o serviço com o Windows, para a organização de hora em hora.
- Adiciona o comando `organizalocal` ao PATH e registra o desinstalador em *Configurações → Aplicativos*.
- Como o instalador não tem assinatura digital paga, o SmartScreen pode avisar na primeira vez. Clique em **Mais informações → Executar assim mesmo**.

**Pacote do Linux:**

- Instala em `/opt/organizalocal` e cria o comando `organizalocal` e o atalho no menu de aplicativos.
- Inicia o serviço ao entrar na sessão, pelo `/etc/xdg/autostart`.
- Os dados de cada usuário ficam em `~/.local/share/OrganizaLocal`.
- Para remover: `sudo apt remove organizalocal`. Os dados são mantidos.

**Gerar os instaladores** (a partir do código):

```bash
./installer/windows/build.sh     # requer makensis (sudo apt install nsis); baixa e confere o Python embutido
./installer/linux/build-deb.sh   # requer dpkg-deb
# saída em dist/
```

### Scripts (alternativa sem instalador)

**Windows:**

1. Instale o **Python 3.10+** em [python.org](https://www.python.org/downloads/), marcando **"Add python.exe to PATH"**.
2. Dê dois cliques em **`scripts\instalar.bat`**.

**Linux:**

```bash
git clone https://github.com/Kaykyduken/organiza-local.git
cd organiza-local
chmod +x scripts/*.sh
./scripts/instalar.sh
organizalocal open        # abre o painel (o atalho do menu faz o mesmo)
```

O script cria `~/.local/share/OrganizaLocal` (permissão 700), o comando `~/.local/bin/organizalocal`, o atalho `.desktop` e a entrada `@reboot` no `crontab`.

### Sem instalar (desenvolvimento)

```bash
./scripts/iniciar.sh          # Linux
scripts\iniciar.bat           # Windows
```

Depois, acesse `http://127.0.0.1:8765`.

### Primeiros passos

1. Aba **Regras**: as 5 regras de exemplo vêm **desativadas**. Revise e ative as que quiser, ou crie novas.
2. Aba **Organização**: clique em **Simular**, confira e depois em **Organizar agora**. Ou espere a execução automática.
3. Aba **Backups**: crie uma regra de backup para as pastas importantes.

### Publicação na Vercel

O site é a pasta `web/`, configurada pelo `vercel.json`. Basta importar o repositório na Vercel com o framework **Other**. Depois, informe a URL em **Configurações → URL do site** ou use `--site` no instalador.

O Chrome/Edge pede uma vez a permissão de **acesso à rede local**: clique em **Permitir**.

## 7. Comandos e scripts de automação

| Comando | O que faz |
|---|---|
| `organizalocal open` | Inicia o serviço em segundo plano, se preciso, e abre o site autenticado |
| `organizalocal serve` | Roda o serviço em primeiro plano (mostra PID e código de pareamento) |
| `organizalocal status` / `stop` | Situação do serviço / encerramento controlado |
| `organizalocal organize [--simular]` | Organiza agora, ou só simula, pelo terminal |
| `organizalocal backup [--job nome]` | Executa as regras de backup |
| `organizalocal relatorio` / `info` / `regras` / `codigo` | Relatório PDF / dados do SO / regras / código de pareamento |

| Script | Uso |
|---|---|
| `scripts/instalar.sh` · `instalar.bat` | Instalação completa (pasta do app, atalhos, início automático) |
| `scripts/desinstalar.sh` · `desinstalar.bat` | Remove o programa e mantém os dados (`--apagar-dados` para apagar tudo) |
| `scripts/verificar_sistema.sh` | Relatório de CPU, memória, disco, processo, permissões, cron e últimas operações, salvo em `reports/` |
| `scripts/backup_agora.sh [nome]` | Backup pelo terminal, com código de saída (ideal para cron) |
| `scripts/agendar_cron.sh [--remover]` | Alternativa via cron: `organize` a cada hora e backup às 02:30 |
| `scripts/iniciar.sh` · `iniciar.bat` | Executa direto do repositório |

## 8. Como testar

```bash
python -m pytest -q                       # ou: cd tests && python -m unittest
```

São **76 testes automatizados** em `tests/`. Eles cobrem:

- cada história de usuário (HU01–HU12);
- integridade SHA-256 e conflitos sem sobrescrever;
- retenção de 5 versões e versões travadas;
- restauração e comparação de backups;
- API (token, CORS, origem bloqueada, pareamento, permissões de perfil);
- extração ZIP com bloqueio de `../`, PDF, agendador e migração da versão 0.9.

Cada teste roda numa pasta temporária isolada.

**Verificação manual reproduzível:**

1. Coloque em Downloads um `trabalho_fatec.pdf`, um `boleto.pdf` e um `foto.jpg`.
2. Ative as regras "Arquivos da faculdade", "Documentos PDF" e "Imagens".
3. Clique em **Simular** e confira:
   - `trabalho_fatec.pdf` → Faculdade (prioridade 8 vence a 5);
   - `boleto.pdf` → exceção, não move;
   - `foto.jpg` → Imagens.
4. Clique em **Organizar agora** e confira as pastas e a aba **Histórico**.
5. Crie uma regra de backup e clique 6 vezes em "Fazer backup agora", alterando um arquivo entre as execuções. Só as 5 versões mais recentes ficam.
6. Rode `./scripts/verificar_sistema.sh`.

Rastreabilidade completa em [`COBERTURA_REQUISITOS.md`](COBERTURA_REQUISITOS.md).

## 9. Prints e documento do projeto

O documento completo do projeto (estrutura de mini TCC, com prints de cada etapa) está em [`docs/OrganizaLocal_Documento_Projeto.docx`](docs/OrganizaLocal_Documento_Projeto.docx). As capturas de tela ficam em [`docs/prints/`](docs/prints):

| Etapa | Print |
|---|---|
| Instalação no Linux | [`t01_instalacao.jpg`](docs/prints/t01_instalacao.jpg) |
| Regras com prioridade ▲/▼ | [`d06_regras_ativas.jpg`](docs/prints/d06_regras_ativas.jpg) |
| Simulação (não move nada) | [`d07_simulacao.jpg`](docs/prints/d07_simulacao.jpg) |
| Resultado e fila de revisão | [`d08_resultado.jpg`](docs/prints/d08_resultado.jpg) |
| Backups com 5 versões | [`d10_backups_versoes.jpg`](docs/prints/d10_backups_versoes.jpg) |
| Aba Sistema (conceitos de SO) | [`d15_sistema.jpg`](docs/prints/d15_sistema.jpg) |
| Testes automatizados | [`t05_testes.jpg`](docs/prints/t05_testes.jpg) |

## 10. Estrutura do repositório

```text
organiza-local/
├── src/organizalocal/   # código-fonte Python (comentado)
│   ├── storage.py       # pasta de dados, config, histórico, SHA-256
│   ├── rules.py         # condições, prioridade, exceções, formato real
│   ├── organizer.py     # simulação, movimentação segura, revisão, ferramentas
│   ├── backups.py       # backups por regras, versões, retenção, restauração
│   ├── archives.py      # ZIP/TAR/RAR/7Z
│   ├── security.py      # token, pareamento, perfis, PIN, senha crítica
│   ├── scheduler.py     # agendador (thread)
│   ├── reports.py       # estatísticas, PDF, limites, vencimentos
│   ├── sysinfo.py       # CPU, memória, disco, processo, variáveis de ambiente
│   ├── server.py        # API HTTP em 127.0.0.1
│   └── cli.py           # comandos de terminal
├── web/                 # site publicado na Vercel (HTML/CSS/JS)
├── scripts/             # instalação e automação (Bash, PowerShell, Batch)
├── installer/           # geração do Setup.exe (NSIS) e do pacote .deb
├── tests/               # testes automatizados
├── docs/                # conceitos de SO, prints e documento do projeto
├── vercel.json
└── README.md
```

## 11. Limitações conhecidas

- O programa precisa estar em execução para organizar sozinho. O instalador o coloca no início automático.
- A organização é por varredura periódica, e não por eventos instantâneos do sistema de arquivos.
- No Linux, `st_ctime` é a data da última mudança de metadados, e não a data de criação.
- RAR e 7Z só podem ser inspecionados, e isso exige o 7-Zip instalado.
- A quarentena reconhece executáveis por extensão e pelos bytes iniciais. **Não é antivírus.**
- Perfis e PIN controlam o painel, mas não substituem as contas de usuário do sistema operacional.
- O site da Vercel depende do navegador permitir o acesso à rede local (Chrome/Edge recentes perguntam). Se não houver permissão, use a interface local em `http://127.0.0.1:8765`.
- Não há criptografia dos backups.
- Foi testado em Linux (Debian/Ubuntu). O Windows foi validado pelo código e pelos scripts, e precisa de teste na máquina de apresentação.

## 12. Possíveis melhorias

Monitoramento por eventos (inotify/ReadDirectoryChangesW), backups incrementais e criptografados, ícone na bandeja do sistema, empacotamento como executável (PyInstaller) e sincronização de regras entre computadores.

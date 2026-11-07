"""OrganizaLocal — organização automática e backup de arquivos.

Pacote escrito apenas com a biblioteca padrão do Python (sem `pip install`),
para que o programa funcione totalmente offline no Windows e no Linux.

Módulos:
    storage    -> pasta de dados, configuração, histórico (JSONL) e SHA-256
    rules      -> categorias, detecção de formato e avaliação das regras
    organizer  -> simulação, organização, fila de revisão, desfazer, ferramentas
    backups    -> backups por regras com versões e retenção (padrão 5)
    archives   -> inspeção/extração segura de ZIP, TAR, RAR e 7Z
    security   -> perfis, PIN, senha crítica, token de sessão e pareamento
    scheduler  -> thread que executa organização/backup periodicamente
    reports    -> estatísticas, relatório PDF e medições de armazenamento
    sysinfo    -> informações do sistema operacional (CPU, memória, disco...)
    server     -> API HTTP local (127.0.0.1) consumida pelo site da Vercel
    cli        -> comandos de terminal (serve, open, stop, organize, backup...)
"""

APP_NAME = "OrganizaLocal"
VERSION = "1.0.0"
DEFAULT_PORT = 8765

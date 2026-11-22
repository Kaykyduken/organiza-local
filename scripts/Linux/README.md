# Scripts para Linux

Com o Python 3.10 ou superior instalado, execute o comando abaixo na raiz do projeto para iniciar o serviço local e abrir o painel no navegador sem instalar o OrganizaLocal.

```bash
bash scripts/Linux/iniciar.sh
```

| Arquivo | O que faz |
| --- | --- |
| [iniciar.sh](iniciar.sh) | Abre o programa sem instalar. Com `status`, consulta a situação do serviço. |
| [instalar.sh](instalar.sh) | Instala o programa, cria atalhos e configura o início automático por padrão. |
| [desinstalar.sh](desinstalar.sh) | Remove a instalação feita pelo script e preserva regras, histórico e backups por padrão. |
| [agendar_cron.sh](agendar_cron.sh) | Configura o cron para organizar arquivos a cada hora e executar backups às 02h30. |
| [backup_agora.sh](backup_agora.sh) | Executa as regras de backup. Informe o nome de uma regra para executar só aquela. |
| [verificar_sistema.sh](verificar_sistema.sh) | Gera um relatório sobre o sistema e o serviço local. |

Se você já configurou o cron com o script antes da mudança de pasta, execute `bash scripts/Linux/agendar_cron.sh` para atualizar o caminho do backup.

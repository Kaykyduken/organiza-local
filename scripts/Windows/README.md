# Scripts para Windows

Com o Python 3.10 ou superior instalado, escolha o arquivo `.bat` e dê dois cliques no Explorador de Arquivos.

| Arquivo para abrir | O que faz |
| --- | --- |
| [iniciar.bat](iniciar.bat) | Inicia o serviço local e abre o painel sem instalar. Com `status` no terminal, consulta a situação do serviço. |
| [instalar.bat](instalar.bat) | Instala o programa, cria atalhos e configura o início automático por padrão. |
| [desinstalar.bat](desinstalar.bat) | Remove a instalação feita pelos scripts e preserva regras, histórico e backups por padrão. |

Os arquivos `instalar.ps1` e `desinstalar.ps1` são chamados automaticamente pelos respectivos arquivos `.bat`. Se você der dois cliques em um `.ps1`, o Windows pode abrir o arquivo no Bloco de Notas.

Para instalar pelo PowerShell, execute este comando na raiz do projeto.

```powershell
.\scripts\Windows\instalar.bat
```

# Rastreabilidade de requisitos

Este documento junta três conjuntos de requisitos:

1. as **histórias de usuário (HU01–HU12)** e os **requisitos (RF01–RF14 / RNF01–RNF10)** do grupo;
2. os pedidos acrescentados (organização de hora em hora, backups por regras, instalador e site na Vercel);
3. os **50 requisitos da versão 0.9** (RF001–RF050), todos mantidos.

**Legenda:** ✅ implementado e testado · ☑️ implementado, mas validado só manualmente ou em parte · ⚠️ parcial ou depende do ambiente.

## 1. Histórias de usuário

| HU | Critérios de aceitação | Onde | Teste |
|---|---|---|---|
| HU01 Organizar por extensão | Uma ou mais extensões; pasta de destino; identifica e aplica | `rules.matches` (`extensions`) · aba Regras | `test_hu01_*` ✅ |
| HU02 Organizar pelo nome | Palavra ou expressão; destino; qualquer posição no nome | `rules.matches` (`keywords`) | `test_hu02_*` ✅ |
| HU03 Prioridade | Define prioridade; a maior vence; indica empate | `rules.evaluate` (`tie`) · badge "mesma prioridade" · fila de revisão | `test_hu03_*` ✅ |
| HU04 Alterar ordem | Lista ordenada; ▲/▼; salvo e usado depois | `Organizer.change_priority`, `ordered_rules` | `test_hu04_*` ✅ |
| HU05 Exceções | Condições de exceção; verificadas antes; editar e excluir | `rule.exceptions` (`skip`/`move`) · editor na aba Regras | `test_hu05_*` ✅ |
| HU06 Consultar regras | Condição, destino, prioridade, estado, possui exceções | Aba Regras · `state.rules` | `test_hu06_*` ✅ |
| HU07 Editar regras | Altera campos; salva; vale nas próximas execuções | `save_rule(payload, id)` | `test_hu07_*` ✅ |
| HU08 Excluir regras | Seleciona; pede confirmação; deixa de aplicar | `rule_delete` exige `confirm` · modal | `test_hu08_*` ✅ |
| HU09 Ativar/desativar | Altera estado; desativada não aplica; estado salvo | `set_enabled` | `test_hu09_*` ✅ |
| HU10 Simular | Mostra os arquivos correspondentes, o destino previsto e não move nada | `Organizer.simulate` · aba Organização | `test_hu10_*` ✅ |
| HU11 Executar | Regras ativas, prioridades e exceções; trata existentes; informa falhas | `Organizer.organize` + `transfer` | `test_hu11_*`, `test_rnf10_*` ✅ |
| HU12 Resultado | Quantidade organizada; falhas com motivo; não informa sucesso falso | Cartão "Resultado da organização" · `status` ok/partial/error | `test_hu12_*` ✅ |

## 2. Requisitos funcionais do grupo

| RF | Implementação |
|---|---|
| RF01 Organizar por extensão | `conditions.extensions` ✅ |
| RF02 Organizar por nome | `conditions.keywords` (e também prefixo, sufixo, glob e regex) ✅ |
| RF03 Pasta de destino | `destination` + "criar se não existir" + destino padrão + projetos ✅ |
| RF04 Definir prioridade | 0–10 ✅ |
| RF05 Alterar prioridade | ▲/▼ e edição ✅ |
| RF06 Exceções | Não mover ou mover para outra pasta ✅ |
| RF07 Consultar regras | Lista ordenada com condições, destino, prioridade, estado e exceções ✅ |
| RF08 Editar regras | Formulário de edição ✅ |
| RF09 Excluir regras | Com confirmação ✅ |
| RF10 Ativar/desativar | Botão Ativar/Desativar ✅ |
| RF11 Identificar conflitos | `matched` mostra todas as regras que batem; empate → revisão; `validate_all` avisa antes ✅ |
| RF12 Simular | Tabela com destino previsto e filtro; exporta JSON ✅ |
| RF13 Executar | Manual, pelo agendador (padrão 60 min) e pelo terminal ✅ |
| RF14 Informar resultados | Cartão de resultado + histórico + relatório PDF ✅ |

## 3. Requisitos não funcionais do grupo

| RNF | Como é atendido |
|---|---|
| RNF01 Desempenho | Varredura com `os.walk`; no mesmo disco usa `os.rename` (sem cópia); duplicados agrupam primeiro por tamanho; limite de 25 000 arquivos por varredura. Testes: 76 em ~16 s ✅ |
| RNF02 Usabilidade | Interface web em português, formulários com exemplos, regras de exemplo prontas (desativadas), simulação antes de mover ✅ |
| RNF03 Segurança | `os.access` antes de mover; pasta de dados protegida; API só em 127.0.0.1 com token e origem validada; perfis/PIN; senha crítica ✅ |
| RNF04 Confiabilidade | Cada falha registrada com motivo; `status` ok/partial/error; movimentação só é registrada como `ok` depois de conferir o SHA-256 ✅ |
| RNF05 Integridade | SHA-256 antes e depois de cada movimentação; rollback se divergir ✅ |
| RNF06 Compatibilidade | Windows 10/11 e Linux, Python 3.10+; scripts para os dois; caminhos com `pathlib`. Testado em Linux; Windows validado por análise e parse dos scripts ☑️ |
| RNF07 Manutenibilidade | Módulos separados por responsabilidade, código comentado, 76 testes ✅ |
| RNF08 Persistência | `config.json` com escrita atômica + versões da configuração ✅ |
| RNF09 Recuperação de erros | `friendly_error`: sem permissão, destino inexistente/inválido, arquivo em uso (WinError 32), disco cheio ✅ |
| RNF10 Segurança operacional | Política definida: renomear (padrão), revisar ou ignorar. Substituir só com confirmação, e guarda cópia antes ✅ |

## 4. Pedidos acrescentados

| Pedido | Implementação |
|---|---|
| Pasta padrão = Downloads | `downloads_directory()` (respeita `XDG_DOWNLOAD_DIR` no Linux) ✅ |
| Organizar de hora em hora por padrão | `organize_schedule = interval/60 min` ✅ |
| Backup por regras, máximo de versões padrão 5 | `backups.py` (origens, destino, filtros, intervalo, ZIP/cópia, retenção) ✅ |
| Rodar offline, Python, Windows e Linux | Somente biblioteca padrão; interface local como alternativa sem internet ✅ |
| Site versionado na Vercel para regras, histórico e backups | `web/` + `vercel.json`; o atalho abre o site com token ☑️ (depende do deploy) |
| Instalação cria a pasta do aplicativo | `instalar.sh` / `instalar.ps1` ✅ |
| Histórico de todas as movimentações | `events.jsonl` + aba Histórico com busca e filtros ✅ |

## 5. Requisitos da versão 0.9 (todos mantidos)

| Requisito | Situação na 1.0 |
|---|---|
| RF001 Regras personalizadas | ✅ |
| RF002 Extensões | ✅ |
| RF003 Categorias | ✅ prontas e personalizadas |
| RF004 Padrões do nome | ✅ palavra, prefixo, sufixo, glob, regex |
| RF005 Tamanho e período | ✅ (no Linux, `ctime` ≠ criação) |
| RF006 Prioridade | ✅ |
| RF007 Exceções | ✅ agora também "não mover" |
| RF008 Duplicar regras | ✅ |
| RF009 Validação | ✅ inclusive aviso de empate antecipado |
| RF010 Testar uma regra | ✅ botão "Testar" |
| RF011 Destino padrão | ✅ |
| RF012 Projetos | ✅ |
| RF013 Compactados | ✅ categoria |
| RF014 Inspeção de compactados | ✅ ZIP/TAR (extração segura); RAR/7Z só listagem, via 7-Zip ⚠️ |
| RF015 Suspeitos e quarentena | ✅ por extensão e por formato disfarçado (não é antivírus) |
| RF016 Temporários e em uso | ✅ extensões temporárias, idade mínima e erro "em uso" |
| RF017 Monitoramento automático | ✅ por varredura periódica |
| RF018 Agendamentos | ✅ intervalo, diária, semanal |
| RF019 Simulação e relatório | ✅ |
| RF020 Sandbox | ✅ |
| RF021 Conflitos de nomes | ✅ |
| RF022 Proteção de arquivos/pastas | ✅ |
| RF023 Exclusões globais | ✅ |
| RF024 Permissões | ✅ `os.access` (ACLs avançadas dependem do SO) |
| RF025 Confirmação e senha crítica | ✅ |
| RF026 Perfis | ✅ com PIN (não substitui as contas do SO) |
| RF027 Desfazer | ✅ |
| RF028 Integridade | ✅ |
| RF029 Duplicados | ✅ |
| RF030 Classificação inteligente | ✅ heurística (extensão + formato real) |
| RF031 Nomes padronizados | ✅ |
| RF032 Nomes incompatíveis | ✅ `clean_name` |
| RF033 Backups | ✅ agora por regras |
| RF034 Comparar/restaurar | ✅ comparação por arquivo |
| RF035 Retenção e versões travadas | ✅ padrão 5 |
| RF036 Alterações externas | ✅ por varredura |
| RF037 Histórico pesquisável | ✅ |
| RF038 Observações | ✅ |
| RF039 Relatórios PDF | ✅ sem ReportLab |
| RF040 Dashboard | ✅ |
| RF041 Limites de armazenamento | ✅ |
| RF042 Vencimentos | ✅ |
| RF043 Interface e temas | ✅ claro/escuro/neon |
| RF044 Abrir backups | ✅ |
| RF045 Pareamento | ✅ token automático pelo atalho + código |
| RF046 Configuração inicial | ✅ Downloads + regras de exemplo |
| RF047 Caminhos monitorados | ✅ aviso de pasta indisponível |
| RF048 Versionar configurações | ✅ |
| RF049 Importar/exportar | ✅ importa também o formato 0.9 |
| RF050 Fila de revisão | ✅ |
| RNF001 SHA-256 com data | ✅ |
| RNF002 Extensões sem diferenciar caixa | ✅ |
| RNF003 Vercel + execução local | ☑️ |
| RNF004 Windows e Linux | ☑️ |
| RNF005 Histórico local | ✅ |
| RNF006 Pasta própria protegida | ✅ |
| RNF007 Comunicação segura com o localhost | ✅ |
| RNF008 Chrome/Edge/Brave recentes | ☑️ depende da permissão de rede local do navegador |

**Mudanças em relação à 0.9:**

- FastAPI, Uvicorn, ReportLab e rarfile foram trocados pela biblioteca padrão, para não precisar de internet nem de compilador.
- O backup passou a ser por regras, com versões de pastas inteiras e manifesto SHA-256.
- A quarentena automática agora é opcional (padrão desligado), já que a organização automática vem ligada. Arquivos disfarçados vão sempre para revisão.

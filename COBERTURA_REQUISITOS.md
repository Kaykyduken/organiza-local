# Rastreabilidade de requisitos

A matriz considera a versão **1.2.0**. Ela preserva as histórias **HU01–HU12**, os requisitos **RF01–RF14 e RNF01–RNF10** do grupo e os requisitos legados **RF001–RF050 e RNF001–RNF008**.

**Evidência de cobertura**

- ✅ O comportamento descrito tem teste automatizado identificado.
- ☑️ A implementação foi inspecionada ou verificada manualmente, ou possui teste parcial.
- ⚠️ Há uma lacuna funcional, dependência de ambiente ou validação ainda pendente.

Os testes de motor e de API exercitam regras, persistência e permissões. Os fluxos de interface foram avaliados separadamente em navegador. A versão disponível na Vercel e os instaladores distribuídos acompanham as respectivas publicações.

## 1. Histórias de usuário

| HU | Critérios de aceitação | Onde | Teste |
|---|---|---|---|
| HU01 Organizar por extensão | Seleciona uma ou mais extensões e aplica a regra ao tipo correspondente | `rules.matches` (`extensions`) · Regras → Tipos e destino | `test_hu01_*` ✅ |
| HU02 Organizar pelo nome | Palavra ou expressão; destino; qualquer posição no nome | `rules.matches` (`keywords`) | `test_hu02_*` ✅ |
| HU03 Prioridade | Define prioridade; a maior vence; indica empate | `rules.evaluate` (`tie`) · badge "mesma prioridade" · fila de revisão | `test_hu03_*` ✅ |
| HU04 Alterar ordem | Lista ordenada; botões Aumentar/Diminuir prioridade; salvo e usado depois | `Organizer.change_priority`, `ordered_rules` | `test_hu04_*` ✅ |
| HU05 Exceções | Condições de exceção; verificadas antes; editar e excluir | `rule.exceptions` (`skip`/`move`) · editor na aba Regras | `test_hu05_*` ✅ |
| HU06 Consultar regras | Condição, destino, prioridade, estado, possui exceções | Aba Regras · `state.rules` | `test_hu06_*` ✅ |
| HU07 Editar regras | Altera campos; salva; vale nas próximas execuções | `save_rule(payload, id)` | `test_hu07_*` ✅ |
| HU08 Excluir regras | Seleciona; pede confirmação; deixa de aplicar | `rule_delete` exige `confirm` · modal | `test_hu08_*` ✅ |
| HU09 Ativar/desativar | Altera estado; desativada não aplica; estado salvo | `set_enabled` | `test_hu09_*` ✅ |
| HU10 Simular | Mostra os arquivos correspondentes e o destino previsto, preservando os arquivos | `Organizer.simulate` · aba Organização · etapa Revisão do assistente, antes de salvar o rascunho | `test_hu10_*`, `test_rascunho_le_arquivos_e_avisa_empate_sem_salvar` ✅ |
| HU11 Executar | Regras ativas, prioridades e exceções; trata existentes; informa falhas | `Organizer.organize` + `transfer` | `test_hu11_*`, `test_rnf10_*` ✅ |
| HU12 Resultado | Quantidade organizada; falhas com motivo; não informa sucesso falso | Cartão "Resultado da organização" · `status` ok/partial/error | `test_hu12_*` ✅ |

## 2. Requisitos funcionais do grupo

| RF | Implementação | Evidência |
|---|---|---|
| RF01 Organizar por extensão | `conditions.extensions` | HU01 ✅ |
| RF02 Organizar por nome | `conditions.keywords`, com opções avançadas de prefixo, sufixo, glob e regex | HU02, `test_categoria_glob_regex_prefixo_sufixo` ✅ |
| RF03 Pasta de destino | Destino por regra, com opção de criar a pasta, destino padrão e projeto | `test_destino_relativo_e_regex_invalida`, `test_hu11_executa_e_preserva_conteudo` ✅ |
| RF04 Definir prioridade | 0 a 10 | `test_prioridade_limitada_entre_0_e_10` ✅ |
| RF05 Alterar prioridade | Botões **Aumentar prioridade** e **Diminuir prioridade** e edição | HU04 ✅ |
| RF06 Exceções | Impede a movimentação ou redireciona para outra pasta | HU05 ✅ |
| RF07 Consultar regras | Lista ordenada com condições, destino, prioridade, estado e exceções | HU06 ✅ |
| RF08 Editar regras | Formulário de edição, incluindo a origem | HU07, `test_edicao_por_interface_antiga_preserva_escopo` ✅ |
| RF09 Excluir regras | Solicita confirmação antes de remover | HU08 ✅ |
| RF10 Ativar/desativar | Estado da regra é salvo e respeitado pelo motor | HU09 ✅ |
| RF11 Identificar conflitos | O motor identifica regras correspondentes, envia empates à revisão e sinaliza possíveis conflitos na validação | `test_hu03_empate_e_indicado`, `test_empate_vai_para_revisao` ✅ |
| RF12 Simular | Tabela com destino previsto e exportação JSON | HU10, `test_exportar_simulacao` ✅ |
| RF13 Executar | Pelo painel, pelo agendador e pelo terminal. Intervalo padrão de 60 min | HU11, `test_agendador_intervalo_e_diario` ✅ |
| RF14 Informar resultados | Resultado com totais e falhas, histórico e relatório PDF | HU12, `test_relatorio_diario`, `test_historico_filtra_periodo_e_simulacao` ✅ |

## 3. Requisitos não funcionais do grupo

| RNF | Como é atendido |
|---|---|
| RNF01 Desempenho | `os.walk`, limite de 25 000 arquivos por varredura de diretórios, renomeação no mesmo volume e agrupamento de duplicados por tamanho antes do hash. Medições de tempo e carga ficam pendentes ☑️ |
| RNF02 Usabilidade | Interface em português, assistentes em três etapas, catálogo pesquisável, ajuda, simulação e preferências de aparência. Evidência funcional no Chrome e em testes parciais de API. A avaliação de usabilidade com usuários fica pendente ☑️ |
| RNF03 Segurança | Pastas protegidas e verificação de acesso. API em `127.0.0.1`, origem validada e token nas ações autenticadas. Pareamento restrito às origens aceitas, perfis com PIN e senha para operações críticas. `test_acao_sem_token_e_negada`, `test_origem_desconhecida_bloqueada`, `test_perfil_com_pin` e `test_senha_critica` ✅ |
| RNF04 Confiabilidade | Registra falhas de movimentação com motivo, informa resultado completo, parcial ou com erro e contabiliza sucesso após conferir o SHA-256. `test_hu12_falha_e_informada_e_nao_conta_como_sucesso` ✅ |
| RNF05 Integridade | Verifica o SHA-256 na origem e no destino. Entre volumes, verifica a cópia antes de remover a origem. Confere o conteúdo em `test_hu11_executa_e_preserva_conteudo`. A verificação em volumes físicos distintos e a injeção de falhas de integridade ficam pendentes ☑️ |
| RNF06 Compatibilidade | Windows 10/11 e Linux com Python 3.10+. A suíte atual foi executada no Windows. Houve verificações anteriores no Linux. A abertura de um terminal gráfico no Linux e a validação integral da instalação atual nas plataformas alvo ficam pendentes ☑️ |
| RNF07 Manutenibilidade | Módulos separados por responsabilidade, instruções de contribuição e 102 testes automatizados executados com `unittest` ✅ |
| RNF08 Persistência | Escrita atômica de `config.json`, versões, restauração e exportação. `test_versoes_da_configuracao`, `test_exportar_importar` e testes das preferências de aparência ✅ |
| RNF09 Recuperação de erros | Mensagens para permissão, dados inválidos, arquivo em uso e falta de espaço. Os testes cobrem falhas de movimentação e de abertura do navegador. Parte dos erros de sistema depende de reprodução no ambiente ☑️ |
| RNF10 Segurança operacional | Renomeia por padrão, oferece revisão ou ignora. Substituição exige confirmação e guarda uma cópia do arquivo anterior. `test_rnf10_conflito_renomeia_sem_sobrescrever`, `test_conflito_politica_revisao_e_ignorar` e `test_previa_de_nome_e_colisao_preservam_arquivo` ✅ |

## 4. Pedidos acrescentados

| Pedido | Implementação |
|---|---|
| Pasta padrão = Downloads | `downloads_directory()` (respeita `XDG_DOWNLOAD_DIR` no Linux) ✅ |
| Organizar de hora em hora por padrão | `organize_schedule = interval/60 min` ✅ |
| Backup por regras, máximo de versões padrão 5 | `backups.py` (origens, destino, filtros, intervalo, ZIP/cópia, retenção) ✅ |
| Rodar offline, Python, Windows e Linux | Somente biblioteca padrão; interface local como alternativa sem internet ✅ |
| Site na Vercel para regras, histórico e backups | `web/` e `vercel.json`. O atalho abre o painel configurado com a sessão autenticada. O acesso depende de publicação, internet e permissão de rede local ☑️ |
| Instalação cria a pasta do aplicativo e oferece o atalho e o início automático | Instalador NSIS, pacote `.deb` e scripts. No Windows, a atualização aguarda o encerramento do serviço. O comando compartilhado pelo instalador e pelo atalho foi exercitado no Windows ☑️ |
| Histórico de todas as movimentações | `events.jsonl` + aba Histórico com busca e filtros ✅ |

## 5. Requisitos da versão 0.9

| Requisito | Situação no código atual |
|---|---|
| RF001 Regras personalizadas | ✅ HU01, HU02 e HU07 |
| RF002 Extensões | ✅ HU01 e `test_extensao_dupla_tar_gz` |
| RF003 Categorias | ✅ Categorias prontas em `test_categoria_glob_regex_prefixo_sufixo`. ☑️ Cadastro de categorias personalizadas |
| RF004 Padrões do nome | ✅ Palavras, prefixo, sufixo, glob e regex. RF02 |
| RF005 Tamanho e período | ✅ `test_tamanho_e_idade`. No Linux, `st_ctime` representa alteração de metadados |
| RF006 Prioridade | ✅ RF04 e RF05 |
| RF007 Exceções | ✅ HU05 |
| RF008 Duplicar regras | ✅ `test_duplicar_regra_nasce_desativada` |
| RF009 Validação | ✅ `test_sem_condicao_e_recusada` e `test_escopo_recursivo_impede_destino_dentro_da_origem`. Possíveis empates aparecem na validação |
| RF010 Testar uma regra | ✅ `test_teste_de_regra_inativa_usa_sua_origem` |
| RF011 Destino padrão | ☑️ Configuração em `default_destination` |
| RF012 Projetos | ☑️ Destino por projeto nas regras em `project_id` |
| RF013 Compactados | ☑️ Categoria predefinida |
| RF014 Inspeção de compactados | ✅ `test_zip_inspecionar_e_extrair`, `test_zip_com_caminho_perigoso_e_bloqueado` e `test_tar_inspecionar`. ☑️ Extração de TAR implementada. ⚠️ Listagem de RAR/7Z depende de 7-Zip ou, para RAR, de `unrar` |
| RF015 Suspeitos e quarentena | ✅ `test_disfarcado_vai_para_revisao_ou_quarentena`. Quarentena automática desativada por padrão |
| RF016 Temporários e em uso | ✅ `test_ignora_temporarios_recentes_e_ocultos` e `test_ignora_downloads_em_andamento`. ☑️ Bloqueios de arquivo dependem do sistema operacional |
| RF017 Monitoramento automático | ✅ `test_padroes_downloads_e_de_hora_em_hora`. A cada 60 minutos por padrão |
| RF018 Agendamentos | ✅ Intervalo e diária em `test_agendador_intervalo_e_diario`. ☑️ Programação semanal implementada |
| RF019 Simulação e relatório | ✅ HU10 e `test_relatorio_diario` |
| RF020 Sandbox | ✅ `test_sandbox_nao_toca_originais` |
| RF021 Conflitos de nomes | ✅ RNF10 |
| RF022 Proteção de arquivos/pastas | ✅ `test_protegidos_e_exclusoes` |
| RF023 Exclusões globais | ✅ `test_protegidos_e_exclusoes` |
| RF024 Permissões | ☑️ `os.access` e tratamento de erros de permissão. ACLs e bloqueios dependem do sistema operacional |
| RF025 Confirmação e senha crítica | ✅ `test_hu08_excluir_exige_confirmacao` e `test_senha_critica` |
| RF026 Perfis | ✅ `test_perfil_com_pin` e `test_permissao_do_perfil` |
| RF027 Desfazer | ✅ `test_desfazer_movimentacao` |
| RF028 Integridade | ✅ `test_hu11_executa_e_preserva_conteudo`. Para os limites de validação, ver RNF05 |
| RF029 Duplicados | ✅ `test_duplicados_e_remocao_segura` |
| RF030 Classificação inteligente | ✅ Heurística de extensão e formato. `test_sugestoes_para_arquivos_sem_regra` e `test_formato_real_pelos_bytes_iniciais` |
| RF031 Nomes padronizados | ✅ `test_renomear_ao_mover` |
| RF032 Nomes incompatíveis | ☑️ Normalização em `clean_name` |
| RF033 Backups | ✅ `test_cria_versao_com_manifesto_e_filtros` |
| RF034 Comparar/restaurar | ✅ `test_comparar_versoes`, `test_restaurar_no_local_original_preserva_atual` e `test_restaurar_em_outra_pasta_e_um_arquivo` |
| RF035 Retenção e versões travadas | ✅ `test_padrao_5_versoes` e `test_retencao_mantem_no_maximo_n_versoes_e_respeita_travadas` |
| RF036 Alterações externas | ☑️ Verificação por varredura |
| RF037 Histórico pesquisável | ✅ `test_historico_filtra_periodo_e_simulacao` |
| RF038 Observações | ☑️ Registro de observações por caminho |
| RF039 Relatórios PDF | ✅ `test_pdf_valido` e `test_relatorio_diario` |
| RF040 Painel | ✅ `test_periodos_e_ultimos_resultados_do_painel` |
| RF041 Limites de armazenamento | ✅ `test_vencimentos_e_limites` |
| RF042 Vencimentos | ✅ `test_vencimentos_e_limites` |
| RF043 Interface e temas | ✅ Persistência em `test_tema_premium_persiste_e_mantem_o_tema_base` e `test_elevacao_dos_controles_permite_desligar_e_restaurar`. ☑️ Animações e feedback visual verificados no Chrome |
| RF044 Abrir backups | ☑️ Abre a pasta de backups pelo sistema operacional |
| RF045 Pareamento | ✅ `test_pareamento_por_codigo` e `test_inicia_servico_e_abre_painel_autenticado`. ☑️ Exibição no terminal verificada no Windows e simulada para o Linux |
| RF046 Configuração inicial | ✅ `test_padroes_downloads_e_de_hora_em_hora`. Regras de exemplo começam desativadas |
| RF047 Caminhos monitorados | ☑️ Aviso de pasta indisponível em `validate_all` |
| RF048 Versionar configurações | ✅ `test_versoes_da_configuracao` |
| RF049 Importar/exportar | ✅ `test_exportar_importar` e `test_migracao_da_versao_09` |
| RF050 Fila de revisão | ✅ `test_empate_vai_para_revisao` e `test_conflito_politica_revisao_e_ignorar` |
| RNF001 SHA-256 com data | ✅ Registros em `events.jsonl`. O hash da movimentação é verificado em `test_hu11_executa_e_preserva_conteudo` |
| RNF002 Extensões sem diferenciar caixa | ✅ `test_hu01_extensao_sem_diferenciar_maiusculas` |
| RNF003 Vercel + execução local | ☑️ Integração e troca testadas no Chrome com duas origens. A Vercel depende da publicação da interface e da permissão de rede local |
| RNF004 Windows e Linux | ☑️ Conforme RNF06 |
| RNF005 Histórico local | ✅ `test_historico_filtra_periodo_e_simulacao` |
| RNF006 Pasta própria protegida | ✅ `test_destino_na_pasta_de_dados_e_bloqueado`. ☑️ Permissões específicas exigem validação no sistema operacional |
| RNF007 Comunicação segura com o localhost | ✅ RNF03 e `test_site_da_vercel_autorizado_com_cors_e_rede_privada` |
| RNF008 Chrome/Edge/Brave recentes | ☑️ Fluxos recentes exercitados no Chrome. A validação da versão atual no Edge e no Brave fica pendente |

**Mudanças em relação à 0.9:**

- FastAPI, Uvicorn, ReportLab e rarfile foram trocados pela biblioteca padrão, para não precisar de internet nem de compilador.
- O backup passou a ser por regras, com versões de pastas inteiras e manifesto SHA-256.
- A quarentena automática é opcional e vem desativada. Executáveis disfarçados vão para revisão com a quarentena desligada e para quarentena quando ela está ligada.

## 6. Requisitos acrescentados e fluxos atuais

Use esta tabela para conferir os fluxos que evoluíram após os requisitos originais.

| Fluxo e critério de aceitação | Onde | Evidência |
|---|---|---|
| Escolher **Pastas específicas** e decidir se entram subpastas, ou usar as **Pastas monitoradas** e acompanhar a lista e a opção geral de subpastas das Configurações | `rule.sources` / `source_recursive` · etapa Origem | `test_escopos_distintos_e_regra_legada`, `test_edicao_por_interface_antiga_preserva_escopo` ✅. Cartões e navegação verificados no Chrome ☑️ |
| Detectar extensões nas origens da regra, consultar contagens, buscar e filtrar por categoria ou estado e manter as marcações ao trocar de filtro ou detectar novamente | **Tipos e destino** · `extensions_scan` · `web/journeys.js` | `test_lista_extensoes_com_contagem_categoria_e_exemplos` ✅. Seleção e filtros verificados em telas larga e estreita no Chrome ☑️ |
| Sinalizar no catálogo quando outra regra ativa já usa uma extensão | `extensions_scan` fornece `used_by` e o catálogo exibe as outras regras ativas | `test_indica_regras_ativas_que_ja_usam_a_extensao` cobre a API ✅. Exibição e exclusão da própria regra foram verificadas no navegador ☑️ |
| Simular o rascunho da regra sem salvar, com aviso de empate | etapa 3 do assistente | `test_rascunho_le_arquivos_e_avisa_empate_sem_salvar`, `test_teste_de_regra_inativa_usa_sua_origem` ✅ |
| Impedir destino dentro da própria origem quando a regra inclui subpastas | `Organizer.save_rule` | `test_escopo_recursivo_impede_destino_dentro_da_origem` ✅ |
| Filtros do histórico por período e por simulação | aba Histórico | `test_historico_filtra_periodo_e_simulacao` ✅ |
| Prévia de renomeação sem sobrescrever arquivos | Ferramentas → renomear | `test_previa_de_nome_e_colisao_preservam_arquivo` ✅ |
| Escolher pasta ou arquivo no diálogo do Windows e reaproveitar o caminho no formulário. Cancelar libera uma nova seleção | `native_picker.py` · botões **Escolher pasta** e **Escolher arquivo** | `test_seletor_e_delegado_sem_perder_o_caminho` cobre a delegação. Abertura, retorno, cancelamento e reabertura verificados no Windows ☑️ |
| Solicitar o código de seis dígitos na tela **Conectar ao programa** e exibi-lo no terminal local. A resposta HTTP confirma a abertura | `/api/pair/show-code` · `cli.open_pairing_terminal` | `test_abre_terminal_para_parear_com_codigo_atualizado` e `test_terminal_rejeita_origem_ausente_e_nao_autorizada` ✅. Console real no Windows, lançadores simulados no Linux ☑️ |
| Alterar **Painel padrão** em **Configurações → Integração**. Ao salvar a troca, a mesma aba abre o endereço escolhido com a sessão atual | `saveSettings` · `config_update` e CORS | `test_troca_para_site_publicado_autoriza_nova_origem` e `test_troca_para_painel_local_confirma_salvamento_a_origem_anterior` ✅. Os dois sentidos foram verificados no Chrome com duas origens de teste. O site precisa carregar a interface desta versão ☑️ |
| Salvar separadamente o **Tema premium**, a animação do fundo e a elevação dos controles (**Desativada**, **Normal**, **Média**, **Máxima**). Com a elevação desligada, o hover e o clique ainda dão retorno visual | **Configurações → Aparência** · `web/styles.css` · `config_update` | `test_tema_premium_persiste_e_mantem_o_tema_base` e `test_elevacao_dos_controles_permite_desligar_e_restaurar` ✅. Animação, pausa, zoom, sombra e retorno de clique verificados no Chrome ☑️ |
| Perfil inválido não remove o acesso administrativo | `security.py` | `test_perfil_invalido_nao_remove_acesso_administrativo` ✅ |

## 7. Validação reproduzível

Execute `python -m unittest discover -s tests -q` na raiz. A suíte atual passou com **102 testes no Windows**.

Para repetir as verificações de interface:

1. Em **Regras → Nova regra**, alterne entre os modos de origem. Adicione uma pasta de teste com arquivos PDF e JPG, avance e clique em **Detectar tipos nas pastas**. Marque extensões, alterne categoria e filtros e confirme as marcações após detectar novamente.
2. No Windows, abra **Escolher pasta**, selecione um caminho, reabra e cancele. Na tela de pareamento, clique em **Enviar código** e use o código mostrado no terminal para conectar.
3. Em **Integração**, altere o painel e salve. Confirme a navegação na mesma aba e a sessão autenticada. Teste a volta a partir de uma publicação que contenha a interface atual.
4. Em **Aparência**, alterne **Animar o fundo** com o Tema premium ativo. Experimente os quatro níveis de elevação e confira o feedback de hover e clique com a opção **Desativada**.

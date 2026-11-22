# Histórico de versões

Todas as mudanças relevantes do OrganizaLocal ficam registradas aqui, da versão mais nova para a mais antiga.

## [1.1.0] — 22/11/2026

Redesenho do painel e reorganização da distribuição.

### Interface

- Novo **Painel "Visão geral"**: indicadores de arquivos organizados (hoje, 7 dias, 30 dias ou total), regras ativas, versões de backup e fila de revisão; cartão da organização automática; alertas e avisos; atividade recente; distribuição por categoria e por regra.
- **Assistente de regra em 3 etapas** (Origem → Tipos e destino → Revisão), com resumo em frase do que a regra fará.
  - A regra pode ter **pastas de origem próprias** (com ou sem subpastas) ou usar as pastas monitoradas nas configurações.
  - **Catálogo de tipos de arquivo** agrupado por categoria, com busca, filtros e o botão "Detectar tipos nas pastas".
  - **Simulação do rascunho antes de salvar**, com aviso de empate de prioridade; depois, "Salvar e ativar" ou "Salvar desativada".
- **Assistente de backup em 3 etapas** (Origem → Destino e frequência → Revisão), com frequência diária, semanal ou a cada X horas e opções avançadas (formato, filtros e retenção).
- **Histórico com filtros** por texto, tipo de atividade, status e período; exportação em CSV e PDF do histórico filtrado.
- Botões de prioridade passaram a se chamar **Aumentar prioridade** / **Diminuir prioridade**.
- Navegação reorganizada: Painel, Regras, Organização, Backups e Histórico; Ferramentas, Segurança, Sistema e Configurações em "Recursos e controle".
- Ajuda contextual ("Saiba mais") nos formulários, rascunhos dos assistentes mantidos durante a navegação e melhorias de acessibilidade.
- Em **Configurações → Integração**, é possível escolher se o ícone do programa abre o painel local ou o site publicado.

### Programa local

- **Seletor nativo de pasta e arquivo no Windows** (`native_picker.py`).
- Regras com escopo próprio (`sources` e `source_recursive`), compatíveis com as regras antigas.
- Validação que impede escolher um destino dentro da própria origem quando a regra inclui subpastas.
- Filtros de período e de simulação na consulta do histórico e PDF do histórico filtrado.

### Distribuição

- Instaladores prontos na pasta [`Instaladores/`](Instaladores/) (`OrganizaLocal-Setup-1.1.0.exe` e `organizalocal_1.1.0_all.deb`), com `SHA256SUMS.txt`.
- Scripts de geração dos instaladores movidos de `installer/` para [`empacotamento/`](empacotamento/).
- Scripts de instalação separados em [`scripts/Linux/`](scripts/Linux/) e [`scripts/Windows/`](scripts/Windows/), cada um com seu guia.

### Testes

- 92 testes automatizados (eram 81), incluindo `tests/test_fluxos.py` para os fluxos guiados da nova interface.

## [1.0.0] — 09/11/2026

Primeira versão entregue: reescrita enxuta e comentada da versão 0.9.

- Motor de regras por extensão, nome, prioridade (0 a 10), exceções e formato real do arquivo (HU01–HU12).
- Simulação, organização segura com SHA-256 e fila de revisão.
- Organização automática de hora em hora e backups por regras com versões, retenção (padrão de 5 versões), versões travadas, restauração e comparação.
- API local em `127.0.0.1:8765`, painel publicado na Vercel e pareamento por código.
- Seletor de extensões nas regras, lido da pasta monitorada.
- Instaladores para Windows (`.exe` com Python embutido) e Linux (`.deb`).
- 81 testes automatizados.

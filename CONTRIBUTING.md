# Guia da equipe — como contribuir com o OrganizaLocal

Este guia é para os integrantes do grupo. A ideia é que todo mundo consiga rodar o programa, mexer no código sem quebrar o trabalho dos outros e explicar a sua parte na apresentação.

## 1. Regras de ouro

1. **Nunca trabalhe direto na `main`.** A `main` é o que está publicado: cada push nela atualiza o site **https://organiza-local.vercel.app** para todos.
2. **Uma branch por tarefa** e, ao terminar, um **pull request (PR)**. Alguém do grupo revisa antes de juntar na `main`.
3. **Rode os testes antes de abrir o PR.** Se algum quebrar, conserte antes.
4. **Comente o código** como no resto do projeto: um comentário curto dizendo *o que* cada bloco faz e *por quê*. Todo mundo precisa conseguir explicar o código na apresentação.
5. **Só biblioteca padrão do Python.** O programa roda offline e sem `pip install` (requisito do projeto). Nada de bibliotecas externas.

## 2. Preparar o computador (uma vez só)

Você precisa de:

- **Python 3.10 ou mais novo.** No Windows, marque **"Add python.exe to PATH"** ao instalar.
- **Git**, ou o **GitHub Desktop** (mais fácil), com a sua conta do GitHub.
- Um editor (VS Code é o recomendado).

Para clonar o repositório:

- **Com o GitHub Desktop:** File → Clone repository → aba GitHub.com → `Kaykyduken/organiza-local` → Clone.
- **Pelo terminal:**

  ```bash
  git clone https://github.com/Kaykyduken/organiza-local.git
  cd organiza-local
  ```

## 3. Rodar o programa a partir do código

Não precisa instalar nada. Na pasta do repositório:

```bash
./scripts/iniciar.sh          # Linux
scripts\iniciar.bat           # Windows (ou dois cliques no arquivo)
```

Depois, acesse `http://127.0.0.1:8765`. Para parar, use `Ctrl+C` no terminal.

> **Já tem o OrganizaLocal instalado no seu PC?** O programa instalado também usa a porta 8765 e a pasta de dados real. Para desenvolver sem misturar as coisas, use outra porta e outra pasta de dados:
>
> ```bash
> # Linux
> ORGANIZALOCAL_PORT=8799 ORGANIZALOCAL_DATA=/tmp/ol-dev ./scripts/iniciar.sh
> ```
>
> ```bat
> REM Windows (Prompt de Comando)
> set ORGANIZALOCAL_PORT=8799
> set ORGANIZALOCAL_DATA=%TEMP%\ol-dev
> scripts\iniciar.bat
> ```
>
> Nesse caso, acesse `http://127.0.0.1:8799`.

**Cuidado:** as regras movem arquivos de verdade. Para testar, prefira o botão **Simular** ou o **sandbox**, ou aponte a pasta monitorada para uma pasta de teste em vez da sua Downloads.

## 4. Rodar os testes

```bash
python -m pytest -q                 # se tiver o pytest
cd tests && python -m unittest      # sem instalar nada
```

Hoje são **81 testes** e todos devem passar. Cada teste roda numa pasta temporária, então nada no seu computador é mexido. **Mudou um comportamento? Ajuste ou crie o teste correspondente.** Os nomes dos testes citam a história de usuário (por exemplo `test_hu10_...`). Se o seu teste cobrir um requisito, atualize também o [`COBERTURA_REQUISITOS.md`](COBERTURA_REQUISITOS.md).

## 5. O fluxo de uma tarefa

### Com o GitHub Desktop

1. **Atualize:** clique em **Fetch origin** e depois em **Pull origin**, se aparecer.
2. **Crie a branch:** Current branch → **New branch** → dê um nome como `backup-agendado` ou `corrige-historico`. Ela deve sair da `main`.
3. **Faça a alteração** e rode os testes.
4. **Faça o commit:** escreva um resumo curto em português (ex.: "Backups: mostra o tamanho de cada versão") → **Commit to …**.
5. **Publique:** clique em **Publish branch**.
6. **Abra o PR:** clique em **Create Pull Request**, descreva o que mudou e como testou, e peça revisão para alguém do grupo.

### Pelo terminal

```bash
git switch main && git pull
git switch -c minha-tarefa
# ... alterações ...
python -m pytest -q
git add -A
git commit -m "Backups: mostra o tamanho de cada versão"
git push -u origin minha-tarefa
# depois abra o pull request no site do GitHub
```

### Revisar e juntar

- Quem revisa lê o código, roda os testes na branch e aprova ou pede ajustes.
- Ao aprovar, use **Squash and merge** para deixar o histórico da `main` limpo. Depois, apague a branch.
- A Vercel costuma gerar um **link de prévia** do site no próprio PR. Use esse link para testar mudanças na interface antes de juntar.

### Deu conflito?

Isso acontece quando duas pessoas mexem no mesmo trecho. Para resolver:

1. Atualize a sua branch com a `main`. No GitHub Desktop: Branch → **Update from main**.
2. Abra os arquivos marcados, escolha o que fica e apague os marcadores `<<<<<<<`, `=======` e `>>>>>>>`.
3. Rode os testes e faça um novo commit.

Se ficar confuso, peça ajuda no grupo **antes** de forçar qualquer coisa. **Nunca** use `git push --force` na `main`.

## 6. Onde fica cada coisa

| Quero mexer em… | Arquivo |
|---|---|
| Regras (condições, prioridade, exceções, formato real) | `src/organizalocal/rules.py` |
| Organização (simular, mover, revisão, desfazer) | `src/organizalocal/organizer.py` |
| Backups, versões e restauração | `src/organizalocal/backups.py` |
| Agendamento (de hora em hora etc.) | `src/organizalocal/scheduler.py` |
| Configuração, histórico e pasta de dados | `src/organizalocal/storage.py` |
| API e permissões | `src/organizalocal/server.py`, `security.py` |
| Informações do sistema (aba Sistema, conceitos de SO) | `src/organizalocal/sysinfo.py` |
| Comandos de terminal | `src/organizalocal/cli.py` |
| Site (telas, formulários, estilos) | `web/app.js`, `web/styles.css`, `web/index.html` |
| Scripts de instalação e automação | `scripts/` |
| Instaladores (Setup.exe e .deb) | `installer/` |
| Documento do projeto e prints | `docs/` |

**Para adicionar uma ação nova na interface:**

1. Crie a função no módulo certo (por exemplo, `organizer.py`).
2. Registre a ação na tabela `actions` do `server.py`, com a permissão adequada.
3. Chame a ação pelo `web/app.js`.
4. Escreva um teste em `tests/`.

## 7. Versões e instaladores

Os instaladores em `web/downloads/` são gerados pelos scripts em `installer/`. **Não edite os binários na mão.** Se uma mudança precisar chegar a quem instala pelo Setup.exe ou pelo .deb, combine com o grupo para gerar os instaladores de novo e atualizar o `SHA256SUMS.txt`.

## 8. Divisão de responsabilidades

Veja a tabela de integrantes no [README](README.md#2-integrantes). Cada um é a referência da sua parte e revisa os PRs que mexem nela, mas todos podem contribuir em qualquer área.

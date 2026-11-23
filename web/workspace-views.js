'use strict';

function backupFrequency(hours) {
  return { 24: 'Todos os dias', 168: 'Semanalmente' }[hours] || `A cada ${String(hours).replace('.', ',')} h`;
}

function backupWizard() {
  const job = UI.backupForm;
  const step = UI.backupStep;
  const frequency = [24, 168].includes(job.interval_hours) ? String(job.interval_hours) : 'custom';
  return `<form class="card wizard" id="backupForm" novalidate>
    <div class="wizard-heading"><h2>${job.id ? 'Editar rotina de backup' : 'Criar rotina de backup'}</h2><span class="small muted">Etapa ${step} de 3</span></div>
    ${wizardProgress(step, ['Origem', 'Destino e frequência', 'Revisão'])}
    <div class="notice err" data-form-error tabindex="-1" role="alert" hidden></div>
    <section class="wizard-step" ${step === 1 ? '' : 'hidden'}><h3 tabindex="-1">O que deseja copiar?</h3>
      <label>Nome da rotina<input name="name" value="${esc(job.name || '')}" placeholder="Exemplo: Documentos de trabalho" maxlength="120"></label>
      ${pathList('sources', 'Pastas ou arquivos para incluir', job.sources || [], true)}
    </section>
    <section class="wizard-step" ${step === 2 ? '' : 'hidden'}><h3 tabindex="-1">Onde e quando guardar as cópias?</h3>
      ${pathField({ name: 'destination', label: 'Pasta para guardar as cópias', value: job.destination, placeholder: 'Pasta de dados do OrganizaLocal' })}
      <p class="small muted">Com o campo vazio, as cópias ficam na pasta de dados do programa. Use outra unidade para guardar cópias fora do disco de origem.</p>
      <label>Frequência<select id="backupFrequency" name="frequency"><option value="24"${selected('24', frequency)}>Todos os dias</option><option value="168"${selected('168', frequency)}>Semanalmente</option><option value="custom"${selected('custom', frequency)}>A cada X horas</option></select></label>
      <label data-backup-interval ${frequency === 'custom' ? '' : 'hidden'}>Intervalo em horas<input name="interval_hours" type="number" min="0.1" max="2160" step="any" value="${job.interval_hours ?? 24}"></label>
      <details class="wizard-advanced"><summary>Formato, filtros e retenção</summary><div class="form">
        <label>Formato<select name="mode"><option value="zip"${selected('zip', job.mode)}>Arquivo compactado ZIP</option><option value="copy"${selected('copy', job.mode)}>Cópia de pastas</option></select></label>
        <label>Quantidade máxima de versões<input name="max_versions" type="number" min="1" max="100" value="${job.max_versions ?? S.config.default_max_versions}"></label>
        <label>Incluir apenas estes tipos<input name="include_extensions" value="${esc((job.include_extensions || []).join(', '))}" placeholder=".docx, .pdf"></label>
        <label>Ignorar nomes ou padrões<input name="exclude_patterns" value="${esc((job.exclude_patterns || []).join(', '))}" placeholder="*.tmp, node_modules"></label>
        <label class="check"><input type="checkbox" name="skip_unchanged" ${job.skip_unchanged === false ? '' : 'checked'}> Criar versão apenas se algo mudou</label>
      </div>
      ${fieldHelp('Uma versão é uma cópia feita em outro momento. Quando a rotina ultrapassa o limite, ela apaga as versões mais antigas que estiverem destravadas.')}</details>
    </section>
    <section class="wizard-step" ${step === 3 ? '' : 'hidden'}><h3 tabindex="-1">Revise a rotina</h3>
      <dl class="wizard-summary"><dt>Nome</dt><dd>${esc(job.name || '')}</dd><dt>Copiar de</dt><dd>${esc((job.sources || []).join(' · '))}</dd><dt>Guardar em</dt><dd>${esc(job.destination || 'Pasta de dados do OrganizaLocal')}</dd><dt>Frequência</dt><dd>${backupFrequency(job.interval_hours)}</dd></dl>
      <p class="notice warn">Manter até <strong>${job.max_versions ?? S.config.default_max_versions} versões</strong>. As cópias mais antigas destravadas são apagadas quando o limite é ultrapassado.</p>
      <label class="check"><input type="checkbox" name="enabled" ${job.enabled === false ? '' : 'checked'}> Executar automaticamente nessa frequência</label>
    </section>
    <footer class="wizard-footer"><button type="button" data-act="bk-cancel">Cancelar</button><div class="row">
      ${step > 1 ? '<button type="button" data-act="bk-back">Voltar</button>' : ''}
      ${step < 3 ? '<button type="button" class="primary" data-act="bk-next">Continuar</button>' : `<button class="primary" type="submit">${job.id ? 'Salvar rotina' : 'Criar rotina de backup'}</button>`}</div></footer>
  </form>`;
}

function readBackupForm(form) {
  const f = new FormData(form);
  const interval = f.get('frequency') === 'custom' ? f.get('interval_hours') : f.get('frequency');
  return { ...UI.backupForm, name: f.get('name').trim(), mode: f.get('mode'), sources: f.getAll('sources'),
    destination: f.get('destination').trim(), max_versions: Number(f.get('max_versions')),
    include_extensions: csv(f.get('include_extensions')), exclude_patterns: csv(f.get('exclude_patterns')),
    interval_hours: Number(interval), skip_unchanged: f.has('skip_unchanged'), enabled: f.has('enabled') };
}

function stepBackup(delta) {
  const form = $('#backupForm');
  const job = readBackupForm(form);
  if (delta > 0 && hasPendingPath(form)) return formError(form, 'Adicione o caminho digitado antes de continuar.');
  if (delta > 0 && UI.backupStep === 1 && (!job.name || !job.sources.length)) return formError(form, 'Informe um nome e adicione pelo menos uma origem.');
  if (delta > 0 && UI.backupStep === 2 && !(job.interval_hours >= 0.1 && job.interval_hours <= 2160 && Number.isInteger(job.max_versions) && job.max_versions >= 1 && job.max_versions <= 100)) {
    return formError(form, 'Use um intervalo entre 0,1 e 2.160 horas e de 1 a 100 versões.');
  }
  UI.backupForm = job;
  UI.backupStep += delta;
  render();
  $('#backupForm .wizard-step:not([hidden]) h3')?.focus();
}

async function cancelBackup() {
  if (UI.backupDirty && !await confirmBox({ title: 'Descartar alterações no backup?', text: 'Os dados desta rotina ainda estão no rascunho.', danger: true, okText: 'Descartar' })) return;
  UI.backupForm = null;
  UI.backupDirty = false;
  render();
}

function beginBackup(job) {
  UI.backupForm = job ? structuredClone(job) : { mode: 'zip', enabled: true, skip_unchanged: true, interval_hours: 24 };
  UI.backupStep = 1;
  UI.backupDirty = false;
  render();
  $('#backupForm .wizard-step:not([hidden]) h3')?.focus();
}

async function saveBackup(form) {
  if (UI.savingBackup || UI.backupStep !== 3) return;
  UI.savingBackup = true;
  formError(form);
  const job = readBackupForm(form);
  const id = job.id;
  const existing = id && S.backup_jobs.find(item => item.id === id);
  try {
    let confirm = false;
    if (existing && job.max_versions < existing.versions.length) {
      confirm = await confirmBox({ title: 'Reduzir o número de versões?', text: 'Salvar este limite pode apagar imediatamente versões mais antigas que estejam destravadas.', danger: true, okText: 'Reduzir limite' });
      if (!confirm) return;
    }
    const { versions, folder, next_run, ...payload } = job;
    await call('backup_job_save', { id, job: payload, confirm: Boolean(confirm) });
    UI.backupForm = null;
    UI.backupDirty = false;
    toast('Rotina de backup salva.');
    await refresh();
  } catch (error) {
    if (form.isConnected) formError(form, error.message);
    else toast(error.message, true);
  } finally { UI.savingBackup = false; }
}

const HISTORY_GROUPS = {
  movement: ['Movimentações', ['move', 'organize', 'review', 'review_decision', 'rename', 'undo', 'undo_reference']],
  simulation: ['Simulações', ['simulate', 'sandbox']],
  backup: ['Backups', ['backup', 'restore', 'backup_job_save', 'backup_job_delete', 'backup_retention', 'backup_lock', 'backup_verify', 'backup_delete']],
  alerts: ['Avisos', ['quarantine', 'quarantine_release', 'quarantine_delete', 'external_change', 'api_error', 'scheduler', 'review']],
  system: ['Sistema e regras', ['install', 'service_start', 'service_stop', 'service_signal', 'config_save', 'config_restore', 'config_import', 'rule_save', 'rule_delete', 'rule_toggle', 'rule_priority', 'profile_switch', 'profile_save', 'report']],
};

function eventTitle(event) {
  return {
    move: 'Arquivo movido', review: 'Arquivo para revisão', organize: 'Organização de arquivos',
    simulate: 'Organização simulada', install: 'Primeira configuração', config_save: 'Configurações atualizadas',
    service_start: 'Aplicativo iniciado', service_stop: 'Aplicativo encerrado',
    service_signal: 'Encerramento solicitado', rule_save: 'Regra salva', backup: 'Cópia de backup',
    undo_reference: 'Movimentação revertida', external_change: 'Alteração detectada em arquivo',
  }[event.operation] || OPS[event.operation] || 'Atividade do aplicativo';
}

function eventSummary(event) {
  if (event.source) return pathName(event.source);
  if (event.rule_name) return event.rule_name;
  if (event.operation === 'organize' && event.moved !== undefined) return `${event.moved} movido(s) · ${event.reviewed || 0} para revisão · ${event.failures || 0} falha(s)`;
  if (event.operation === 'simulate') return `${event.processed} analisados · ${event.would_move} seriam movidos`;
  if (['backup', 'backup_job_save', 'backup_job_delete', 'profile_switch'].includes(event.operation)) return event.detail || '';
  return '';
}

function historyEntry(event, undone) {
  const canUndo = allowed('restore') && ['move', 'review', 'rename'].includes(event.operation) && event.status === 'ok'
    && event.source && event.destination && event.sha256 && !undone.has(event.id);
  return `<li class="timeline-entry">
    <span class="dashboard-icon">${icon(event.operation === 'backup' ? 'backups' : event.source ? 'arquivo' : 'historico')}</span>
    <div class="timeline-body"><div class="row"><strong>${esc(eventTitle(event))}</strong>${statusBadge(event.status)}</div>
      <p>${esc(eventSummary(event) || (event.status === 'error' ? 'Consulte os detalhes para ver o motivo.' : ''))}</p>
      <details class="field-help"><summary>Ver detalhes</summary><dl>
        ${[['Origem', event.source], ['Destino', event.destination], ['Regra', event.rule_name], ['Motivo', event.reason], ['Registro original', event.detail]].filter(([, value]) => value).map(([label, value]) => `<dt>${label}</dt><dd>${esc(value)}</dd>`).join('')}
        <dt>Tipo de evento</dt><dd>${esc(event.operation)}</dd>
      </dl></details>
    </div>
    <div class="timeline-meta"><time datetime="${esc(event.timestamp)}">${when(event.timestamp)}</time><div class="row">
      ${canUndo ? `<button data-act="undo" data-id="${esc(event.id)}">Desfazer</button>` : ''}
      ${allowed('settings') ? `<button class="ghost" data-act="note-for" data-type="operation" data-ref="${esc(event.id)}">Adicionar observação</button>` : ''}</div></div>
  </li>`;
}

function viewHistorico() {
  const f = UI.historyFilters;
  const rows = UI.history || [];
  const undone = new Set([...(S.latest || []), ...rows].filter(event => event.operation === 'undo_reference').map(event => event.reference));
  const result = UI.historyError ? `<p role="alert" class="notice err">${esc(UI.historyError)}</p><button data-act="history-load">Tentar novamente</button>` :
    UI.history === null || UI.historyLoading ? '<p class="muted" role="status">Lendo o histórico…</p>' :
      rows.length ? `<ul class="timeline">${rows.map(event => historyEntry(event, undone)).join('')}</ul>` : empty('Nenhuma atividade encontrada para estes filtros.');
  return `${header('Histórico', 'Acompanhe o que aconteceu com seus arquivos, regras e backups.')}
    <form class="card filter-bar" id="historyForm">
      <label>Buscar<input name="q" type="search" value="${esc(f.q || '')}" placeholder="Arquivo, pasta ou regra"></label>
      <label>Tipo<select name="group"><option value="">Todas as atividades</option>${Object.entries(HISTORY_GROUPS).map(([key, [label]]) => `<option value="${key}"${selected(key, f.group)}>${label}</option>`).join('')}</select></label>
      <label>Status<select name="status"><option value="">Todos</option>${Object.entries(STATUS_TEXT).map(([key, label]) => `<option value="${key}"${selected(key, f.status)}>${label}</option>`).join('')}</select></label>
      <label>De<input name="from_date" type="date" value="${esc(f.from_date || '')}"></label>
      <label>Até<input name="to_date" type="date" value="${esc(f.to_date || '')}"></label>
      <div class="row"><button class="primary" type="submit">Aplicar filtros</button><button type="button" data-act="history-clear">Limpar</button></div>
    </form>
    <section class="card workspace-section"><div class="spread"><h2>Atividade ${rows.length ? `<span class="small muted">${rows.length} registros${rows.length === 500 ? ' recentes' : ''}</span>` : ''}</h2>
      <div class="row">${rows.length ? '<button data-act="history-export">Exportar resultados</button>' : ''}${allowed('analyze') ? (supported('rule_scope') ? '<button data-act="history-pdf">PDF do histórico filtrado</button>' : '<button data-act="report-today">PDF de hoje</button>') : ''}</div></div>${result}</section>`;
}

async function loadHistory() {
  if (UI.historyLoading) return;
  UI.historyLoading = true;
  UI.historyError = '';
  if (TAB === 'historico') render();
  try {
    const filters = { ...UI.historyFilters, operations: HISTORY_GROUPS[UI.historyFilters.group]?.[1] };
    const entries = await call('history', { filters, limit: 500 });
    UI.history = supported('rule_scope') ? entries : entries.filter(event => {
      const day = (event.timestamp || '').slice(0, 10);
      return (!filters.from_date || day >= filters.from_date) && (!filters.to_date || day <= filters.to_date) &&
        (!filters.operations || filters.operations.includes(event.operation));
    });
  } catch (error) { UI.historyError = error.message; UI.history = []; }
  finally { UI.historyLoading = false; if (S && TAB === 'historico') render(); }
}

function exportHistory() {
  const cell = value => {
    const text = String(value ?? '');
    return '"' + (/^[\s]*[=+@-]/.test(text) ? "'" : '') + text.replaceAll('"', '""') + '"';
  };
  const rows = [['Data e hora', 'Atividade', 'Status', 'Arquivo', 'Destino', 'Regra'],
    ...UI.history.map(event => [event.timestamp, eventTitle(event), STATUS_TEXT[event.status] || event.status, event.source, event.destination, event.rule_name])];
  saveBlob(new Blob(['\ufeff', rows.map(row => row.map(cell).join(';')).join('\r\n')], { type: 'text/csv;charset=utf-8' }), 'historico-organizalocal.csv');
}

const TOOL_GROUPS = [
  ['Organizar e analisar', [
    ['suggestions', 'Classificar arquivos', 'Sugere categorias e regras para arquivos encontrados nas pastas monitoradas.'],
    ['duplicates', 'Encontrar duplicados', 'Compara o conteúdo dos arquivos e mostra quais cópias são iguais.'],
    ['rename', 'Renomear arquivo', 'Confira o nome previsto antes de renomear um arquivo.'],
    ['projects', 'Projetos', 'Use uma pasta de projeto como destino de uma regra.'],
    ['categories', 'Categorias personalizadas', 'Agrupe extensões para usá-las nas regras.'],
  ]],
  ['Arquivos e formatos', [
    ['archive', 'Arquivos compactados', 'Veja o conteúdo de um pacote antes de extrair.'],
    ['storage', 'Armazenamento e limites', 'Meça o espaço das pastas e configure alertas.'],
    ['deadlines', 'Vencimentos', 'Receba lembretes sobre datas de documentos.'],
    ['notes', 'Observações', 'Registre anotações sobre arquivos, regras, operações e backups.'],
  ]],
  ['Segurança e testes', [
    ['integrity', 'Verificar integridade', 'Compare o conteúdo de um arquivo com o código de verificação esperado.'],
    ['sandbox', 'Testar em cópias', 'Experimente as regras em cópias dos arquivos monitorados.'],
  ]],
  ['Relatórios e backups', [
    ['reports', 'Relatório em PDF', 'Baixe o relatório de atividades de um dia.'],
    ['filehistory', 'Versões em backup', 'Procure cópias anteriores de um arquivo.'],
  ]],
];
const LIST_LABELS = { limits: ['Adicionar limite', 'Salvar limites'], due_dates: ['Adicionar vencimento', 'Salvar vencimentos'],
  projects: ['Adicionar projeto', 'Salvar projetos'], categories: ['Adicionar categoria', 'Salvar categorias'] };

function listRow(columns, item = {}) {
  return `<div class="form le-row">
    ${columns.map(column => {
    const value = column.key === 'max_mb' ? (item.max_bytes ? item.max_bytes / 1048576 : '') :
      Array.isArray(item[column.key]) ? item[column.key].join(', ') : item[column.key] ?? '';
    return column.kind ? pathField({ label: column.label, kind: column.kind, name: column.key, value }) :
      `<label>${column.label}<input name="${column.key}" type="${column.type || 'text'}" value="${esc(value)}" ${column.ph ? `placeholder="${esc(column.ph)}"` : ''}></label>`;
  }).join('')}
    <button type="button" class="danger" data-act="le-remove">Remover</button></div>`;
}

function listEditor(name, columns, items) {
  const [add, save] = LIST_LABELS[name];
  return `<div class="list-editor" data-list="${name}">${(items || []).map(item => listRow(columns, item)).join('')}
    <div class="row list-actions"><button type="button" data-act="le-add" data-cols='${esc(JSON.stringify(columns))}'>${add}</button>
      <button type="button" class="primary" data-act="le-save" data-list="${name}" disabled>${save}</button></div></div>`;
}

function toolForm(id) {
  const field = (id, label, kind) => pathField({ id, label, kind });
  switch (id) {
    case 'suggestions': return '<button class="primary" data-act="tool" data-tool="suggestions">Analisar pastas monitoradas</button>' + toolResult(id);
    case 'duplicates': return '<p class="muted">A análise só lista cópias idênticas. Escolha individualmente as que deseja apagar.</p><button class="primary" data-act="tool" data-tool="duplicates">Procurar duplicados</button>' + toolResult(id);
    case 'archive': return `<div class="tool-fields">${field('arcPath', 'Arquivo compactado', 'file')}${field('arcDest', 'Pasta de extração', 'folder')}</div>
      <p class="small muted">ZIP e TAR podem ser extraídos. RAR e 7Z podem ser consultados quando o 7-Zip está disponível.</p>
      <div class="row"><button class="primary" data-act="arc-inspect">Ver conteúdo</button><button data-act="arc-extract">Extrair para a pasta</button></div>${toolResult(id)}`;
    case 'sandbox': return `<p class="muted">O teste grava cópias em uma pasta separada do aplicativo. As regras são aplicadas nessas cópias.</p><div class="row"><button class="primary" data-act="sandbox-run">Criar teste em cópias</button><button data-act="sandbox-list">Ver testes salvos</button></div>
      ${toolResult(id)}${(UI.tools.sandboxes || []).map(item => `<div class="spread compact-line"><span>${esc(item.id)} · ${item.files} arquivo(s)</span><button class="danger" data-act="sandbox-del" data-id="${esc(item.id)}">Apagar cópias</button></div>`).join('')}`;
    case 'integrity': return `<div class="tool-fields">${field('intPath', 'Arquivo a verificar', 'file')}</div><details class="wizard-advanced"><summary>Comparar com um código SHA-256</summary>
      <p class="small muted">Se você tem um código da fonte do arquivo, compare para saber se o conteúdo é igual. Use a quarentena para arquivos suspeitos.</p><label>Código esperado<input id="intHash"></label></details>
      <button class="primary" data-act="integrity">Verificar arquivo</button>${toolResult(id)}`;
    case 'rename': return `<div class="tool-fields">${field('renPath', 'Arquivo para renomear', 'file')}</div>
      <label>Modelo de nome<input id="renPattern" placeholder="{date}_{name}.{ext}"></label>
      ${fieldHelp('Por exemplo, {date}_{name}.{ext} pode transformar notas.pdf em 2026-11-22_notas.pdf. A extensão original é preservada.') }
      <button class="primary" data-act="rename" ${supported('rule_scope') ? '' : 'disabled'}>Pré-visualizar novo nome</button>
      ${!supported('rule_scope') ? '<p class="small muted">A prévia requer uma versão atualizada do serviço local.</p>' : ''}${toolResult(id)}`;
    case 'reports': return `<div class="tool-fields"><label>Dia do relatório<input id="repDay" type="date" value="${esc((S.timestamp || '').slice(0, 10))}"></label></div>
      <button class="primary" data-act="report">Gerar e baixar PDF</button>`;
    case 'filehistory': return `<div class="tool-fields">${field('fhPath', 'Local original do arquivo', 'file')}</div>
      <div class="row"><button class="primary" data-act="file-history">Procurar versões</button>${dashboardLink('backups', 'Ver rotinas de backup')}</div>${toolResult(id)}`;
    case 'storage': return `<div class="row"><button class="primary" data-act="storage-now">Medir espaço</button><button data-act="storage-hist">Ver medições</button></div>${toolResult(id)}
      <h3 id="storageLimits" tabindex="-1">Limites de espaço</h3><p class="small muted">O painel avisa quando o uso atingir 90% do limite.</p>
      ${listEditor('limits', [{ key: 'path', label: 'Pasta (vazio para todas as monitoradas)', kind: 'folder' }, { key: 'category', label: 'Categoria (opcional)' }, { key: 'max_mb', label: 'Limite em MB', type: 'number' }], S.config.limits)}`;
    case 'deadlines': return `<h3 id="dueDocuments" tabindex="-1">Lembretes de documentos</h3><p class="small muted">O painel avisa nos 30 dias anteriores à data escolhida.</p>
      ${listEditor('due_dates', [{ key: 'description', label: 'Descrição' }, { key: 'file', label: 'Documento (opcional)', kind: 'file' }, { key: 'due', label: 'Data de vencimento', type: 'date' }], S.config.due_dates)}`;
    case 'projects': return listEditor(id, [{ key: 'name', label: 'Nome do projeto' }, { key: 'directory', label: 'Pasta do projeto', kind: 'folder' }], S.config.projects);
    case 'categories': return listEditor(id, [{ key: 'name', label: 'Nome da categoria' }, { key: 'exts', label: 'Extensões', ph: '.psd, .ai' }], Object.entries(S.config.categories || {}).map(([name, exts]) => ({ name, exts })));
    case 'notes': return `<form id="noteForm" class="form">
      <label>Tipo de referência<select name="type"><option value="file">Arquivo</option><option value="rule">Regra</option><option value="operation">Operação</option><option value="backup">Backup</option></select></label>
      <div class="two">${pathField({ label: 'Referência da observação', name: 'ref', kind: 'file', placeholder: 'Arquivo, nome de regra ou outra referência' })}</div>
      <label class="full">Texto<textarea name="text" required></textarea></label><div><button class="primary">Salvar observação</button></div></form>
      ${S.notes.slice().reverse().map(note => `<div class="spread compact-line"><div><strong>${esc(note.ref)}</strong><p>${esc(note.text)}</p><span class="small muted">${when(note.updated)}</span></div><button class="danger" data-act="note-del" data-id="${esc(note.id)}">Apagar observação</button></div>`).join('')}`;
  }
  return '';
}

function viewFerramentas() {
  const selectedTool = TOOL_GROUPS.flatMap(([, tools]) => tools).find(([key]) => key === UI.activeTool);
  if (selectedTool) {
    const [key, title, description] = selectedTool;
    return header(title, description, '<button data-act="tool-back">Voltar às ferramentas</button>') +
      `<section class="card workspace-section tool-workspace">${toolForm(key)}</section>`;
  }
  return header('Ferramentas', 'Escolha uma tarefa para abrir os controles e ver os resultados.') +
    TOOL_GROUPS.map(([group, tools]) => `<section class="tool-group"><h2>${group}</h2><div class="tool-tiles">
      ${tools.map(([key, title, description]) => `<button class="card tool-tile" data-act="tool-open" data-tool="${key}">
        <span class="dashboard-icon">${icon('ferramentas')}</span><strong>${title}</strong><span>${description}</span><span class="tile-open">Abrir ${icon('seta')}</span>
      </button>`).join('')}</div></section>`).join('');
}

const PROFILE_PRESETS = {
  viewer: ['read'],
  operator: ['read', 'analyze', 'organize', 'rules', 'backups'],
  administrator: ['*'],
};

function viewSeguranca() {
  const c = S.config;
  const editing = UI.editProfile;
  const chosenPermissions = editing?.permissions || PROFILE_PRESETS.viewer;
  const canEdit = allowed('settings');
  return `${header('Segurança', 'Gerencie o que pode ser analisado, movido ou acessado pelo painel.')}
    <div class="settings-grid">
      <section class="card workspace-section"><h2 id="quarantineList" tabindex="-1">Quarentena ${badge(S.quarantine.length)}</h2>
        <p>Arquivos sinalizados ficam isolados na pasta de dados. A análise usa extensões e assinaturas de arquivo.</p>
        <label class="check"><input type="checkbox" id="qAuto" ${c.quarantine_risky ? 'checked' : ''} ${canEdit ? '' : 'disabled'}> Isolar executáveis e arquivos com extensão disfarçada automaticamente</label>
        ${fieldHelp('A quarentena separa arquivos sinalizados pelas regras do OrganizaLocal. Use um antivírus para avaliar se um arquivo isolado é seguro.') }
        ${S.quarantine.length ? `<ul class="plain-list">${S.quarantine.map(file => `<li class="spread compact-line"><div><strong>${esc(file.name)}</strong><p class="small muted">${esc(file.format)} · ${bytes(file.bytes)}</p></div>
          ${allowed('delete') ? `<div class="row"><button data-act="q-release" data-name="${esc(file.name)}">Liberar…</button><button class="danger" data-act="q-delete" data-name="${esc(file.name)}">Apagar arquivo</button></div>` : ''}</li>`).join('')}</ul>` : empty('Nenhum arquivo está isolado.')}
      </section>
      <section class="card workspace-section"><h2>Proteção de arquivos</h2><form id="protForm">
        <fieldset ${canEdit ? '' : 'disabled'}><legend>Pastas e arquivos ignorados</legend>
        <p class="small muted">Pastas protegidas também bloqueiam operações de movimentação. Pastas ignoradas ficam fora das varreduras.</p>
        ${pathList('protected', 'Adicionar caminho protegido', c.protected_paths)}
        ${pathList('ex_paths', 'Adicionar pasta ignorada', c.exclusions.paths)}
        <div class="form"><label>Nomes exatos a ignorar<input name="ex_names" value="${esc(c.exclusions.names.join(', '))}" placeholder="rascunho.txt, privado.pdf"></label>
          <label class="two">Extensões a ignorar<input name="ex_exts" value="${esc(c.exclusions.extensions.join(', '))}" placeholder=".iso, .torrent"></label></div>
        <button class="primary" type="submit">Salvar proteções</button></fieldset></form>
      </section>
      <section class="card workspace-section"><h2>Acesso e permissões</h2>
        <p>Perfil atual: <strong>${esc(S.active_profile)}</strong>.</p>
        ${c.profiles.map(profile => `<div class="spread compact-line"><div><strong>${esc(profile.name)}</strong> ${profile.has_pin ? badge('PIN', 'info') : ''}
          <p class="small muted">${profile.permissions.includes('*') ? 'Acesso administrativo' : `${profile.permissions.length} permissões`}</p></div><div class="row">
          ${profile.name !== S.active_profile ? `<button data-act="profile-switch" data-name="${esc(profile.name)}" data-pin="${profile.has_pin ? 1 : 0}">Usar perfil</button>` : badge('Ativo', 'ok')}
          ${canEdit ? `<button data-act="profile-edit" data-name="${esc(profile.name)}">Editar</button>${profile.name !== S.active_profile ? `<button class="danger" data-act="profile-del" data-name="${esc(profile.name)}">Excluir perfil</button>` : ''}` : ''}</div></div>`).join('')}
        ${canEdit ? `<form id="profileForm" class="tool-fields"><h3>${editing ? 'Editar perfil' : 'Criar perfil'}</h3>
          <label>Nome do perfil<input name="name" value="${esc(editing?.name || '')}" ${editing ? 'readonly' : ''} required></label>
          <label>Permissões<select id="profilePreset"><option value="viewer" ${editing ? '' : 'selected'}>Somente leitura</option><option value="operator">Operador</option><option value="administrator">Administrador</option><option value="custom" ${editing ? 'selected' : ''}>Personalizar</option></select></label>
          <p id="profileHelp" class="small muted">${editing ? 'Escolha as operações permitidas no painel.' : 'Pode consultar o painel e o histórico.'}</p>
          <label>PIN ${editing?.has_pin ? 'novo (opcional)' : '(opcional)'}<input name="pin" inputmode="numeric" type="password" pattern="[0-9]{4,8}" title="De 4 a 8 dígitos"></label>
          <details id="profileAdvanced" ${editing ? 'open' : 'hidden'}><summary>Permissões individuais</summary><div class="choice-list">
            ${Object.entries(S.permissions).map(([key, label]) => `<label class="check"><input type="checkbox" name="perm" value="${key}" ${chosenPermissions.includes('*') || chosenPermissions.includes(key) ? 'checked' : ''}> ${esc(label)}</label>`).join('')}</div></details>
          ${fieldHelp('O PIN controla a troca de perfis dentro do painel. As permissões de arquivos do Windows continuam a valer.') }
          <div class="row"><button class="primary">Salvar perfil</button>${editing ? '<button type="button" data-act="profile-cancel">Cancelar edição</button>' : ''}</div></form>` : ''}
      </section>
      <section class="card workspace-section"><h2>Senha para operações críticas</h2><p>${badge(c.critical_password_enabled ? 'Ativada' : 'Desativada', c.critical_password_enabled ? 'ok' : '')} Usada ao restaurar ou remover arquivos e configurações protegidas.</p>
        ${canEdit ? `<form id="passForm" class="tool-fields">${c.critical_password_enabled ? '<label>Senha atual<input name="current" type="password" required autocomplete="current-password"></label>' : ''}
          <label>Nova senha<input name="new" type="password" required minlength="6" autocomplete="new-password"></label>
          <div class="row"><button class="primary">${c.critical_password_enabled ? 'Alterar senha' : 'Definir senha'}</button>
          ${c.critical_password_enabled ? '<button class="danger" type="button" data-act="password-remove">Remover senha</button>' : ''}</div></form>` : ''}
        <details class="wizard-advanced"><summary>Conexão local e origens autorizadas</summary><p>Estes endereços podem se comunicar com o serviço local após o pareamento.</p>
          <ul>${S.allowed_origins.map(origin => `<li>${esc(origin)}</li>`).join('')}</ul>
          ${canEdit ? '<button class="danger" data-act="revoke">Revogar todos os acessos</button>' : ''}</details>
      </section>
    </div>`;
}

function updateProfilePreset() {
  const preset = $('#profilePreset').value;
  $('#profileAdvanced').hidden = preset !== 'custom';
  $('#profileHelp').textContent = { viewer: 'Pode consultar o painel e o histórico.',
    operator: 'Pode simular, organizar e gerenciar regras e backups.',
    administrator: 'Pode alterar a segurança, remover arquivos e usar todas as funções.',
    custom: 'Escolha as operações permitidas no painel.' }[preset];
  if (preset !== 'custom') $$('#profileForm [name=perm]').forEach(input => {
    input.checked = PROFILE_PRESETS[preset].includes('*') || PROFILE_PRESETS[preset].includes(input.value);
  });
}

const reading = value => typeof value === 'number' && value > 0 ? bytes(value) : 'Indisponível';

function viewSistema() {
  const d = UI.sysinfo;
  const actions = '<button data-act="sys-refresh">Atualizar</button>' + (d ? '<button data-act="sys-copy">Copiar diagnóstico</button>' : '');
  const title = header('Sistema', 'Acompanhe o funcionamento do serviço local e o espaço disponível.', actions);
  if (UI.sysinfoError) return title + `<p class="notice err" role="alert">${esc(UI.sysinfoError)}</p>`;
  if (!d) return title + '<p role="status" class="card">Lendo as informações do serviço…</p>';
  const scheduled = d.scheduler.running ? 'Agendador ativo' : 'Agendador parado';
  return title + `<div class="system-overview">
    ${section('Serviço local', `${badge('Ativo', 'ok')}<p>${esc(d.system.os)} ${esc(d.system.release)} · Em execução há ${Math.floor(d.process.uptime_seconds / 60)} min</p>`)}
    ${section('Automação', `${badge(scheduled, d.scheduler.running ? 'ok' : 'warn')}<p>${d.scheduler.running ? `Verifica a cada ${d.scheduler.check_every_seconds} s` : 'Verificação automática indisponível'}</p><p>Próxima execução: ${d.scheduler.running ? when(d.scheduler.next_organize) : '—'}</p>`)}
    ${section('Uso de recursos', `<dl class="wizard-summary"><dt>Memória do aplicativo</dt><dd>${reading(d.process.rss_bytes)}</dd><dt>Memória disponível</dt><dd>${d.memory.total ? bytes(d.memory.available) : 'Indisponível'}</dd><dt>Núcleos</dt><dd>${d.cpu.cores || 'Indisponível'}</dd></dl>`)}
  </div>
  ${d.scheduler.last_error ? `<p class="notice err" role="alert">${esc(d.scheduler.last_error)}</p>` : ''}
  ${section('Espaço disponível', d.disks.length ? `<ul class="plain-list">${d.disks.filter(disk => !disk.same_disk_as_previous).map(disk => `<li class="compact-line"><div class="spread"><strong>${esc(disk.label)}</strong><span>${bytes(disk.free)} livres de ${reading(disk.total)}</span></div>
    <div class="meter" aria-hidden="true"><i style="width:${disk.percent_used}%"></i></div></li>`).join('')}</ul>` : empty('Leitura de armazenamento indisponível.'))}
  ${section('Pastas acompanhadas', `<ul>${monitoredFolders().map(folder => `<li>${esc(folder)}</li>`).join('') || '<li>Nenhuma pasta configurada</li>'}</ul>`)}
  <details class="card"><summary>Diagnóstico avançado</summary><dl class="wizard-summary">
    <dt>Versões</dt><dd>Python ${esc(d.system.python)} · ${esc(d.system.machine)}</dd><dt>Processo</dt><dd>PID ${d.process.pid} · PPID ${d.process.ppid ?? '—'}</dd>
    <dt>Threads</dt><dd>${d.process.threads.map(esc).join(', ')}</dd><dt>Processador</dt><dd>${esc(d.cpu.model || 'Indisponível')}</dd>
    <dt>Interpretador</dt><dd>${esc(d.system.executable)}</dd><dt>Pasta de dados</dt><dd>${esc(d.data_dir.path)}</dd><dt>Permissões</dt><dd>${esc(d.data_dir.permissions)}</dd>
    ${Object.entries(d.environment).map(([name, value]) => `<dt>${esc(name)}</dt><dd>${esc(value)}</dd>`).join('')}</dl></details>`;
}

async function loadSystem() {
  if (UI.sysinfoLoading) return;
  UI.sysinfoLoading = true;
  UI.sysinfoError = '';
  try { UI.sysinfo = await call('sysinfo'); }
  catch (error) { UI.sysinfoError = error.message; }
  finally { UI.sysinfoLoading = false; if (S && TAB === 'sistema') render(); }
}

async function copyDiagnostic() {
  const d = UI.sysinfo;
  const text = [`OrganizaLocal ${S.app.version}`, `Sistema: ${d.system.os} ${d.system.release}`,
    `Agendador: ${d.scheduler.running ? 'ativo' : 'parado'}`, `Memória do serviço: ${reading(d.process.rss_bytes)}`,
    `Discos consultados: ${d.disks.filter(disk => !disk.same_disk_as_previous).length}`].join('\n');
  try { await navigator.clipboard.writeText(text); toast('Diagnóstico copiado.'); }
  catch { showModal('Diagnóstico para suporte', `<label>Resumo<textarea readonly>${esc(text)}</textarea></label>`, false); }
}

function monitoredFolders() {
  return [...new Set([...S.config.watch_dirs, ...S.rules.filter(rule => rule.enabled).flatMap(rule => rule.sources || [])])];
}

function renameExample(pattern) {
  if (!pattern.trim()) return 'notas.pdf';
  const date = (S.timestamp || '').slice(0, 10);
  const [year, month, day] = date.split('-');
  const parsed = { name: 'notas', ext: 'pdf', date, year, month, day, timestamp: date.replaceAll('-', '') + '_120000', seq: '001' };
  const name = pattern.replace(/\{(\w+)\}/g, (full, label) => parsed[label] ?? full);
  return name.toLowerCase().endsWith('.pdf') ? name : name + '.pdf';
}

function viewConfig() {
  const c = S.config;
  const sch = c.organize_schedule;
  const days = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];
  const categories = [['foldersSettings', 'Pastas monitoradas'], ['scheduleSettings', 'Automação'],
    ['conflictSettings', 'Arquivos e conflitos'], ['backupSettings', 'Backups'], ['appearanceSettings', 'Aparência'],
    ['integrationSettings', 'Integração'], ['configRecovery', 'Recuperação']];
  return `${header('Configurações', 'Escolha como o aplicativo acompanha suas pastas e abre o painel.')}
    <div class="card settings-links" aria-label="Seções das configurações">${categories.map(([id, label]) => `<a href="#${id}">${label}</a>`).join('')}</div>
    <form id="configForm" class="settings-form">
      <fieldset ${allowed('settings') ? '' : 'disabled'}>
      ${section('Pastas monitoradas', `<p>Regras gerais procuram arquivos nessas pastas. Regras com origem própria mantêm sua seleção.</p>
        ${pathList('watch_dirs', 'Adicionar pasta monitorada', c.watch_dirs)}
        <label class="check"><input type="checkbox" name="recursive" ${c.recursive ? 'checked' : ''}> Incluir subpastas das origens gerais</label>`, 'id="foldersSettings"')}
      ${section('Organização automática', `<div class="form">
        <label>Frequência<select name="frequency" id="scheduleFrequency">${[['interval', 'A cada intervalo'], ['daily', 'Todos os dias'], ['weekly', 'Semanalmente'], ['off', 'Desligada']].map(([key, label]) => `<option value="${key}"${selected(key, sch.frequency)}>${label}</option>`).join('')}</select></label>
        <label data-frequency="interval" ${sch.frequency === 'interval' ? '' : 'hidden'}>Intervalo em minutos<input name="interval_minutes" type="number" min="1" max="10080" value="${sch.interval_minutes}" ${sch.frequency === 'interval' ? '' : 'disabled'}></label>
        <label data-frequency="daily weekly" ${['daily', 'weekly'].includes(sch.frequency) ? '' : 'hidden'}>Horário<input name="time" type="time" value="${esc(sch.time)}" ${['daily', 'weekly'].includes(sch.frequency) ? '' : 'disabled'}></label>
        <label data-frequency="weekly" ${sch.frequency === 'weekly' ? '' : 'hidden'}>Dia da semana<select name="weekday" ${sch.frequency === 'weekly' ? '' : 'disabled'}>${days.map((day, index) => `<option value="${index}"${selected(index, Number(sch.weekday))}>${day}</option>`).join('')}</select></label>
        <label class="check full"><input type="checkbox" name="organize_on_start" ${c.organize_on_start ? 'checked' : ''}> Organizar quando o serviço iniciar</label>
        </div><p class="small muted">Próxima execução programada: ${S.scheduler.running && S.scheduler.next_organize ? when(S.scheduler.next_organize) : 'sem horário programado'}</p>`, 'id="scheduleSettings" tabindex="-1"')}
      ${section('Arquivos e conflitos', `<label>Quando já existe um arquivo com o mesmo nome<select name="conflict_policy">${['rename', 'review', 'skip'].map(key => `<option value="${key}"${selected(key, c.conflict_policy)}>${conflictLabel(key)}</option>`).join('')}</select></label>
        ${pathField({ name: 'default_destination', label: 'Destino quando nenhuma regra corresponder', value: c.default_destination, placeholder: 'Vazio para manter o arquivo onde está' })}
        <details class="wizard-advanced"><summary>Espera e renomeação automática</summary><div class="form">
          <label>Aguardar arquivo terminar de ser salvo (segundos)<input name="min_file_age_seconds" type="number" min="0" max="86400" value="${c.min_file_age_seconds}"></label>
          <label class="two">Modelo de nome ao mover<input name="rename_pattern" id="configRename" value="${esc(c.rename_pattern)}" placeholder="{date}_{name}.{ext}"></label>
          <p class="small muted full">Exemplo: notas.pdf → <output id="configRenameExample">${esc(renameExample(c.rename_pattern))}</output></p></div></details>`, 'id="conflictSettings"')}
      ${section('Backups e retenção', `<label>Versões padrão para novas rotinas<input name="default_max_versions" type="number" min="1" max="100" value="${c.default_max_versions}"></label><p class="small muted">Cada rotina pode escolher um limite próprio.</p>${dashboardLink('backups', 'Gerenciar rotinas de backup')}`, 'id="backupSettings"')}
      ${section('Aparência', `<div class="appearance-controls">
        <label>Tema base<select name="theme">${[['claro', 'Claro'], ['escuro', 'Escuro'], ['neon', 'Neon']].map(([key, name]) => `<option value="${key}"${selected(key, c.theme)}>${name}</option>`).join('')}</select></label>
        ${supported('control_elevation') ? `<label>Elevação dos botões
          <select name="control_elevation" aria-describedby="elevation-setting-help">${[['off', 'Desativada'], ['normal', 'Normal'], ['medium', 'Média'], ['max', 'Máxima']].map(([key, name]) => `<option value="${key}"${selected(key, c.control_elevation)}>${name}</option>`).join('')}</select>
          <small id="elevation-setting-help">Controla o zoom, a sombra e o brilho ao passar o mouse.</small>
        </label>` : ''}
        </div>
        <label class="premium-setting">
          <span class="premium-setting-sample" aria-hidden="true"></span>
          <span><strong id="premium-theme-label">Tema premium</strong><small id="premium-theme-help">${supported('premium_theme')
            ? 'Ativa o fundo de cores difusas por todo o painel. Escolha abaixo se ele fica animado.'
            : 'Atualize o OrganizaLocal para usar o fundo neon animado.'}</small></span>
          <input type="checkbox" name="premium_theme" role="switch" aria-labelledby="premium-theme-label" aria-describedby="premium-theme-help" ${c.premium_theme ? 'checked' : ''} ${supported('premium_theme') ? '' : 'disabled'}>
        </label>
        ${supported('premium_motion') ? `<label class="check premium-motion-setting">
          <input type="checkbox" name="premium_motion" ${c.premium_motion !== false ? 'checked' : ''}>
          <span><strong>Animar o fundo</strong><small>Controla o movimento das cores quando o Tema premium está ativo.</small></span>
        </label>` : ''}`, 'id="appearanceSettings"')}
      ${section('Integração', `<label>Painel padrão<select name="launch_mode" id="launchMode" aria-describedby="launch-mode-help"><option value="local" ${c.site_url ? '' : 'selected'}>Painel local</option><option value="web" ${c.site_url ? 'selected' : ''}>Site publicado</option></select></label>
        <p id="launch-mode-help" class="small muted">Ao mudar de painel e salvar, esta aba abre o endereço escolhido. O atalho do programa também passa a usar essa preferência.</p>
        <label data-site-field ${c.site_url ? '' : 'hidden'}>URL do site publicado na Vercel<input name="site_url" value="${esc(c.site_url || 'https://organiza-local.vercel.app')}" type="url" ${c.site_url ? '' : 'disabled'}></label>
        <details class="wizard-advanced"><summary>Origens autorizadas</summary><p class="small muted">O painel local funciona no próprio computador. Autorize outros endereços apenas quando precisar que se comuniquem com o serviço.</p>
          <label>Outras origens autorizadas (uma por linha)<textarea name="extra_origins">${esc((c.extra_origins || []).join('\n'))}</textarea></label></details>`, 'id="integrationSettings"')}
      <div class="settings-save"><div><strong id="settingsStatus" role="status">Configurações salvas</strong><p class="field-error" data-form-error role="alert" tabindex="-1" hidden></p></div>
        <button class="primary" type="submit" id="settingsSubmit" disabled>Salvar alterações</button></div>
      </fieldset>
    </form>
    ${allowed('settings') ? section('Exportação e recuperação', `<p>Transfira suas regras e preferências ou recupere uma configuração anterior.</p><div class="row">
      <button data-act="cfg-export">Exportar configuração</button><label class="btn file-control">Importar configuração<input type="file" id="cfgImport" accept=".json,application/json"></label>
      <button data-act="cfg-versions">Listar versões anteriores</button></div>
      ${UI.tools.versions ? `<ul class="plain-list">${UI.tools.versions.map(version => `<li class="spread compact-line"><span>${when(version.timestamp)}<small class="muted"> · ${esc(version.filename)}</small></span><button data-act="cfg-restore" data-file="${esc(version.filename)}">Restaurar versão</button></li>`).join('')}</ul>` : ''}`, 'id="configRecovery"') :
      '<p class="notice info">O perfil atual pode consultar as configurações.</p>'}`;
}

function dirtySettings() {
  UI.configDirty = true;
  $('#settingsStatus').textContent = 'Alterações não salvas';
  $('#settingsSubmit').disabled = false;
  $$('#configRecovery :is(button, input)').forEach(control => { control.disabled = true; });
}

async function saveSettings(form) {
  if (UI.savingConfig || !UI.configDirty) return;
  const data = new FormData(form);
  const c = S.config;
  const frequency = data.get('frequency');
  const mode = data.get('launch_mode');
  const site = String(data.get('site_url') || '').trim();
  formError(form);
  if (hasPendingPath(form)) return formError(form, 'Adicione a pasta digitada antes de salvar.');
  if (mode === 'web' && !site) return formError(form, 'Informe a URL do site ou selecione Painel local.');
  let panel;
  try {
    panel = mode === 'web' ? new URL(site) : new URL('/', API);
    if (!['http:', 'https:'].includes(panel.protocol) || panel.username || panel.password ||
        (mode === 'local' && !['127.0.0.1', 'localhost'].includes(panel.hostname))) {
      throw new Error();
    }
    panel.hash = '';
  } catch {
    return formError(form, 'Informe um endereço HTTP ou HTTPS válido para o painel.');
  }
  const sch = c.organize_schedule;
  const changes = {
    watch_dirs: data.getAll('watch_dirs'), recursive: data.has('recursive'), organize_on_start: data.has('organize_on_start'),
    organize_schedule: { frequency, interval_minutes: frequency === 'interval' ? Number(data.get('interval_minutes')) : sch.interval_minutes,
      time: ['daily', 'weekly'].includes(frequency) ? data.get('time') : sch.time,
      weekday: frequency === 'weekly' ? Number(data.get('weekday')) : sch.weekday },
    conflict_policy: data.get('conflict_policy'), min_file_age_seconds: Number(data.get('min_file_age_seconds')),
    default_destination: data.get('default_destination').trim(), rename_pattern: data.get('rename_pattern'),
    default_max_versions: Number(data.get('default_max_versions')), site_url: mode === 'local' ? '' : panel.href.replace(/\/+$/, ''),
    theme: data.get('theme'), extra_origins: lines(data.get('extra_origins')),
  };
  if (supported('premium_theme')) changes.premium_theme = data.has('premium_theme');
  if (supported('premium_motion')) changes.premium_motion = data.has('premium_motion');
  if (supported('control_elevation')) changes.control_elevation = data.get('control_elevation');
  const submit = $('#settingsSubmit');
  UI.savingConfig = true;
  submit.disabled = true;
  try {
    const config = await call('config_update', { changes });
    UI.configDirty = false;
    toast('Configurações salvas.');
    const savedSiteChanged = config.site_url !== (c.site_url || '');
    const alreadyAtDestination = panel.origin === location.origin && (mode === 'local' ||
      (panel.pathname === location.pathname && panel.search === location.search));
    if (savedSiteChanged && !alreadyAtDestination) {
      panel.hash = new URLSearchParams({ token: TOKEN, api: API });
      location.replace(panel);
      return;
    }
    await refresh();
  } catch (error) {
    if (form.isConnected) formError(form, error.message);
    else toast(error.message, true);
  } finally { UI.savingConfig = false; if (submit.isConnected) submit.disabled = !UI.configDirty; }
}

function hasPendingPath(form) {
  return $$('.path-list [data-path-input]', form).some(input => !input.closest('[data-scoped][hidden]') && input.value.trim());
}

async function preserveDraftOnLeave() {
  if (UI.savingConfig || UI.savingRule || UI.savingBackup) return false;
  if (TAB === 'config' && UI.configDirty) {
    if (!await confirmBox({ title: 'Sair sem salvar?', text: 'As alterações das configurações serão descartadas.', danger: true, okText: 'Descartar e sair' })) return false;
    UI.configDirty = false;
  }
  if (TAB === 'regras' && UI.ruleForm && $('#ruleForm')) {
    if (hasPendingPath($('#ruleForm'))) {
      formError($('#ruleForm'), 'Adicione ou apague o caminho digitado antes de sair do assistente.');
      return false;
    }
    UI.ruleForm = readRuleForm($('#ruleForm'));
    if (UI.ruleDirty) toast('Rascunho guardado nesta sessão. Volte em Regras para continuar.');
  }
  if (TAB === 'backups' && UI.backupForm && $('#backupForm')) {
    if (hasPendingPath($('#backupForm'))) {
      formError($('#backupForm'), 'Adicione ou apague o caminho digitado antes de sair do assistente.');
      return false;
    }
    UI.backupForm = readBackupForm($('#backupForm'));
    if (UI.backupDirty) toast('Rascunho guardado nesta sessão. Volte em Backups para continuar.');
  }
  return true;
}

async function busyButton(button, message, action) {
  if (!('disabled' in button)) return action();
  if (button.disabled) return;
  const original = button.textContent;
  button.disabled = true;
  button.textContent = message;
  try { return await action(); }
  finally { button.textContent = original; button.disabled = false; }
}

async function previewRename(button) {
  const path = $('#renPath').value.trim();
  const pattern = $('#renPattern').value.trim();
  if (!path || !pattern) return toast('Escolha um arquivo e informe o modelo de nome.', true);
  return busyButton(button, 'Preparando prévia…', async () => {
    const preview = await run('rename_preview', { path, pattern }, { reload: false });
    if (!preview || !button.isConnected) return;
    if (preview.source === preview.destination) return toast('O modelo mantém o nome atual.');
    const confirm = await confirmBox({ title: 'Confirmar novo nome?', text: `<p>Antes <b>${esc(pathName(preview.source))}</b></p><p>Depois <b>${esc(pathName(preview.destination))}</b></p>`, okText: 'Renomear arquivo' });
    if (!confirm) return;
    const result = await run('rename_file', { path, pattern, expected: preview.destination }, { reload: false, success: 'Arquivo renomeado.' });
    if (result) { UI.tools.rename = result; render(); }
  });
}

function simulationSummary(sim) {
  const summary = sim.summary || {};
  const blocked = (summary.tie || 0) + (summary.suspicious || 0) + (sim.policy === 'review' ? summary.conflict || 0 : 0);
  const ignored = (summary.busy || 0) + (summary.excluded || 0) + (summary.exception || 0) + (summary.already || 0);
  return `<div class="result-counts">${[['Analisados', sim.count], ['Seriam movidos', sim.would_move], ['Sem regra', summary.no_match || 0], ['Ignorados ou em uso', ignored], ['Para revisão', blocked]].map(([label, number]) => `<div><span>${label}</span><strong>${number}</strong></div>`).join('')}</div>`;
}

function simulationHtml(sim) {
  const unmatched = sim.summary.no_match || 0;
  return `<section class="card workspace-section"><div class="spread"><div><h2 id="simulationResult" tabindex="-1">${sim.only_rule_name ? `Teste da regra ${esc(sim.only_rule_name)}` : 'Simulação da organização'}</h2><p class="small muted">${when(sim.timestamp)} · Nenhum arquivo foi movido.</p></div>
    <button data-act="sim-export">Exportar simulação</button></div>
    ${simulationSummary(sim)}
    ${unmatched ? `<div class="notice spread"><span>${unmatched} arquivo(s) ficaram sem regra correspondente.</span>${allowed('rules') ? '<button data-act="rule-new">Criar regra para estes arquivos</button>' : ''}</div>` : ''}
    <div class="filter-bar"><label>Buscar arquivo<input type="search" id="simSearch" value="${esc(UI.simSearch || '')}" placeholder="Nome ou caminho"></label>
      <label>Resultado<select id="simFilter"><option value="todos">Todos</option>${Object.entries(S.action_labels).map(([key, label]) => `<option value="${key}"${selected(key, UI.simFilter)}>${esc(label)}</option>`).join('')}</select></label></div>
    <div id="simulationRows"></div></section>`;
}

function renderSimulationRows() {
  const container = $('#simulationRows');
  if (!container) return;
  const input = normalizeSearch(UI.simSearch);
  const filter = UI.simFilter;
  const pageSize = 60;
  const rows = UI.simulation.rows.filter(item => normalizeSearch(item.source || item.name).includes(input) &&
    (filter === 'todos' || item.action === filter || (filter === 'move' && item.action === 'default')));
  const endPage = Math.max(0, Math.ceil(rows.length / pageSize) - 1);
  const page = Math.min(UI.simPage || 0, endPage);
  const items = rows.slice(page * pageSize, (page + 1) * pageSize);
  container.innerHTML = items.length ? `<ul class="simulation-rows">${items.map(item => {
    const canCreate = item.action === 'no_match' && allowed('rules');
    const extension = (item.name?.match(/(\.[a-z0-9]{1,14})$/i) || [])[1] || '';
    const origin = item.source?.replace(/[\\/][^\\/]+$/, '') || '';
    const target = item.destination && !(item.action === 'conflict' && UI.simulation.policy === 'skip');
    return `<li><div class="simulation-file"><strong>${esc(item.name)}</strong>${badge(S.action_labels[item.action] || item.action, ACTION_KIND[item.action])}
      ${item.rule_name ? `<small>${esc(item.rule_name)}</small>` : ''}</div>
      <details class="field-help"><summary>Ver detalhes</summary><dl class="wizard-summary"><dt>Origem</dt><dd>${esc(item.source)}</dd>
        ${target ? `<dt>Destino previsto</dt><dd>${esc(item.destination)}</dd>` : ''}
        ${item.reason ? `<dt>Motivo</dt><dd>${esc(item.reason)}</dd>` : ''}</dl></details>
      ${canCreate ? `<button class="ghost" data-act="rule-new" data-ext="${esc(extension.toLowerCase())}" data-origin="${esc(origin)}">Criar regra</button>` : ''}</li>`;
  }).join('')}</ul>
  ${endPage > 0 ? `<div class="spread"><button data-act="sim-page" data-page="${page - 1}" ${page === 0 ? 'disabled' : ''}>Anterior</button><span class="small muted">Página ${page + 1} de ${endPage + 1}</span><button data-act="sim-page" data-page="${page + 1}" ${page === endPage ? 'disabled' : ''}>Próxima</button></div>` : ''}` : empty('Nenhum arquivo neste filtro.');
}

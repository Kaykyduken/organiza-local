'use strict';

// Componentes usados nos formulários do aplicativo e nos assistentes.
const fieldHelp = text => `<details class="field-help"><summary>Saiba mais</summary><p>${esc(text)}</p></details>`;
const selected = (value, current) => value === current ? ' selected' : '';
const pathName = path => String(path || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop() || path;
const supported = feature => Boolean(S.app.features?.[feature]);
const section = (title, content, extra = '') => `<section class="card workspace-section" ${extra}><h2>${title}</h2>${content}</section>`;

let selectingNativePath = false;

function pickerButton(kind, label) {
  return supported('native_picker') ? `<button type="button" data-act="path-picker" data-kind="${kind}" ${selectingNativePath ? 'disabled' : ''}>${label}</button>` : '';
}

function pathField({ label, name = '', id = '', value = '', kind = 'folder', placeholder = 'Caminho completo' }) {
  return `<div class="path-field"><label>${label}<input data-path-input ${id ? `id="${id}"` : ''} ${name ? `name="${name}"` : ''} value="${esc(value)}" placeholder="${esc(placeholder)}"></label>
    ${pickerButton(kind, kind === 'folder' ? 'Escolher pasta' : 'Escolher arquivo')}</div>`;
}

function pathItem(name, value) {
  return `<li><span title="${esc(value)}">${esc(pathName(value))}</span><small>${esc(value)}</small>
    <input type="hidden" name="${name}" value="${esc(value)}">
    <button type="button" class="ghost" data-act="path-remove" aria-label="Remover ${esc(value)}">Remover</button></li>`;
}

function pathList(name, label, values = [], files = false) {
  return `<div class="path-field path-list" data-path-list="${name}">
    <ul class="path-items" aria-label="${label}">${values.map(value => pathItem(name, value)).join('')}</ul>
    <div class="path-entry"><label>${label}<input data-path-input placeholder="Cole um caminho completo"></label>
      <div class="row">${pickerButton('folder', 'Escolher pasta')}${files ? pickerButton('file', 'Escolher arquivo') : ''}<button type="button" data-act="path-add">Adicionar ${files ? 'origem' : 'pasta'}</button></div>
    </div>
    <p class="field-error" data-path-error role="alert" hidden></p>
  </div>`;
}

function changePath(field) {
  field.dispatchEvent(new Event('change', { bubbles: true }));
}

function addPath(field, value) {
  value = value.trim();
  const input = $('[data-path-input]', field);
  const error = $('[data-path-error]', field);
  if (error) error.hidden = true;
  if (!value) {
    if (error) { error.textContent = 'Escolha uma pasta ou informe o caminho completo.'; error.hidden = false; }
    input.focus();
    return;
  }
  if (field.dataset.pathList) {
    const same = (a, b) => S.app.os === 'nt' ? a.toLowerCase() === b.toLowerCase() : a === b;
    if (!$$('input[type=hidden]', field).some(item => same(item.value, value))) {
      $('.path-items', field).insertAdjacentHTML('beforeend', pathItem(field.dataset.pathList, value));
    }
    input.value = '';
  } else {
    input.value = value;
  }
  changePath(field);
}

async function chooseNativePath(button) {
  if (selectingNativePath || button.disabled) return;
  const field = button.closest('.path-field');
  const label = button.textContent;
  const feedback = $('[data-path-error]', field);
  if (feedback) feedback.hidden = true;
  selectingNativePath = true;
  $$('[data-act="path-picker"]').forEach(control => { control.disabled = true; });
  button.textContent = 'Aguardando seleção…';
  try {
    const { path } = await call('select_path', { kind: button.dataset.kind });
    if (path && field.isConnected) addPath(field, path);
  } catch (error) {
    if (feedback && field.isConnected) {
      feedback.textContent = error.message;
      feedback.hidden = false;
    } else {
      toast(error.message, true);
    }
  } finally {
    selectingNativePath = false;
    button.textContent = label;
    $$('[data-act="path-picker"]').forEach(control => { control.disabled = false; });
    if (button.isConnected && document.activeElement === document.body) button.focus();
  }
}

function wizardProgress(step, names) {
  return `<ol class="wizard-progress" aria-label="Etapas">${names.map((name, index) => `<li class="${index + 1 === step ? 'current' : ''}" ${index + 1 === step ? 'aria-current="step"' : ''}><span>${index + 1}</span>${name}</li>`).join('')}</ol>`;
}

function formError(form, message = '') {
  const box = $('[data-form-error]', form);
  box.hidden = !message;
  box.textContent = message;
  if (message) box.focus();
}

function setDraftDirty(form) {
  if (form?.id === 'ruleForm') {
    UI.ruleDirty = true;
    UI.rulePreview = null;
    $('[data-rule-preview]', form).innerHTML = '';
    const activate = $('[data-act=rule-activate]', form);
    if (activate) {
      activate.disabled = supported('rule_scope') && allowed('analyze');
      activate.classList.toggle('primary', !activate.disabled);
    }
    $('[data-act=rule-preview]', form).classList.add('primary');
    const scoped = $('[name=sourceMode]:checked', form)?.value === 'scoped';
    const specific = $('[data-scoped]', form);
    const hideSpecific = !scoped;
    if (UI.ruleStep === 1 && specific.hidden !== hideSpecific) formError(form);
    specific.hidden = hideSpecific;
    const monitored = $('[data-monitored]', form);
    if (monitored) monitored.hidden = scoped;
    updateRuleSentence(form);
  }
  if (form?.id === 'backupForm') UI.backupDirty = true;
}

const FILE_GROUPS = {
  Documentos: 'pdf doc docx txt rtf odt md',
  Planilhas: 'xls xlsx csv ods',
  Apresentações: 'ppt pptx odp',
  Imagens: 'jpg jpeg png gif webp bmp svg heic',
  Vídeos: 'mp4 mov mkv avi webm',
  Áudios: 'mp3 wav flac aac ogg m4a',
  Compactados: 'zip rar 7z tar gz tar.gz',
  Instaladores: 'exe msi msix',
  'Livros digitais': 'epub mobi',
  Código: 'py js ts html css json xml java c cpp cs',
};
const fileGroupSearch = { Documentos: 'word texto acrobat', Planilhas: 'excel calculo números', Apresentações: 'powerpoint slides', Imagens: 'fotos fotografia', Áudios: 'som músicas' };
const extensionList = text => [...new Set(csv(text).map(ext => '.' + ext.toLowerCase().replace(/^\.+/, '')))];

function catalogHtml(inventory, selected, ruleId) {
  const detected = new Map((inventory?.extensions || []).map(item => [item.ext, item]));
  const groups = new Map(Object.entries(FILE_GROUPS).map(([name, values]) => [name, values.split(' ').map(v => '.' + v)]));
  const included = new Set([...groups.values()].flat());
  for (const ext of new Set([...detected.keys(), ...selected])) {
    if (included.has(ext)) continue;
    const group = detected.get(ext)?.category || 'Outros';
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(ext);
  }
  return [...groups].map(([group, extensions], index) => {
    const chips = extensions.map(ext => {
      const item = detected.get(ext);
      const otherRules = (inventory?.used_by?.[ext] || item?.used_by || []).filter(rule => rule.id !== ruleId);
      const usage = otherRules.length === 1 ? `Usada em ${otherRules[0].name}` : `Usada em ${otherRules.length} regras ativas`;
      return `<label class="extchip ${selected.has(ext) ? 'on' : ''}" data-ext="${esc(ext)}" data-found="${item?.count || 0}" title="${esc(item?.examples?.join(', ') || '')}">
        <input type="checkbox" name="ext" value="${esc(ext)}" ${selected.has(ext) ? 'checked' : ''}><span class="mono">${esc(ext)}</span>${item ? `<small>${item.count} ${item.count === 1 ? 'arquivo' : 'arquivos'}</small>` : ''}
        ${otherRules.length ? `<small class="ext-usage" title="${esc(otherRules.map(rule => rule.name).join(', '))}">${esc(usage)}</small>` : ''}</label>`;
    }).join('');
    return `<details class="type-group" data-category="${esc(group)}" data-search="${esc(group + ' ' + (fileGroupSearch[group] || ''))}" data-common="${Object.hasOwn(FILE_GROUPS, group)}" ${index === 0 || extensions.some(v => selected.has(v)) ? 'open' : ''}>
      <summary><strong>${esc(group)}</strong><span class="type-group-count" data-type-count></span></summary>
      <div class="type-group-body">
        ${group === 'Instaladores' ? '<p class="small muted">A política de quarentena continua valendo para executáveis.</p>' : ''}
        <div class="extchips">${chips}</div>
        <button type="button" class="linkbtn" data-act="ext-group"></button>
      </div>
    </details>`;
  }).join('');
}

function syncCatalogCategories(form) {
  const control = $('#extCategory', form);
  const category = control.value;
  control.replaceChildren(new Option('Todas as categorias', ''));
  $$('.type-group', form).forEach(group => {
    control.add(new Option(group.dataset.category, group.dataset.category));
  });
  if ([...control.options].some(option => option.value === category)) control.value = category;
  filterCatalog(form);
}

function filterCatalog(form) {
  const query = normalizeSearch($('#extFilter', form).value);
  const mode = $('#extMode', form).value;
  const category = $('#extCategory', form).value;
  let shown = 0;
  let selectedCount = 0;
  $$('.type-group', form).forEach(group => {
    const inCategory = !category || category === group.dataset.category;
    const titleMatch = normalizeSearch(group.dataset.search).includes(query);
    let checked = 0;
    let visible = 0;
    let checkedVisible = 0;
    for (const chip of $$('.extchip', group)) {
      const marked = $('input', chip).checked;
      if (marked) checked += 1;
      chip.hidden = !inCategory || !(titleMatch || normalizeSearch(chip.dataset.ext).includes(query)) ||
        (mode === 'found' && Number(chip.dataset.found) === 0) ||
        (mode === 'selected' && !marked) ||
        (mode === 'other' && group.dataset.common === 'true');
      if (!chip.hidden) {
        visible += 1;
        if (marked) checkedVisible += 1;
      }
    }
    selectedCount += checked;
    group.hidden = visible === 0;
    $('[data-type-count]', group).textContent = checked
      ? `${checkedVisible} de ${visible} marcadas`
      : `${visible} ${visible === 1 ? 'tipo' : 'tipos'}`;
    $('[data-act=ext-group]', group).textContent = checkedVisible === visible ? 'Desmarcar exibidas' : 'Marcar exibidas';
    if (!group.hidden) {
      shown += 1;
      if (query || category || mode !== 'all') group.open = true;
    }
  });
  $('[data-selected-types]', form).textContent = `${selectedCount} ${selectedCount === 1 ? 'extensão selecionada' : 'extensões selecionadas'}`;
  $('[data-empty-types]', form).hidden = shown !== 0;
}

function catalogInventoryStatus(inventory) {
  if (!inventory) return '';
  const { total_files: total, without_extension: withoutExtension } = inventory;
  const scanned = total === 1 ? '1 arquivo analisado' : `${total} arquivos analisados`;
  return withoutExtension ? `${scanned} · ${withoutExtension} sem extensão` : scanned;
}

async function refreshCatalog(form) {
  if (!form || !allowed('analyze')) return;
  const button = $('[data-act=ext-scan]', form);
  if (button.disabled) return;
  const indicator = $('[data-inventory-status]', form);
  const scoped = $('[name=sourceMode]:checked', form)?.value === 'scoped';
  const data = new FormData(form);
  const sources = scoped ? data.getAll('sources') : S.config.watch_dirs;
  if (!sources.length) return;
  const params = { paths: sources, recursive: scoped ? data.has('source_recursive') : S.config.recursive };
  button.disabled = true;
  indicator.textContent = 'Buscando tipos nas origens selecionadas…';
  try {
    const inventory = await call('extensions_scan', params);
    if (!form.isConnected) return;
    UI.extInv = inventory;
    const marked = new Set(new FormData(form).getAll('ext'));
    $('#extPicker', form).innerHTML = catalogHtml(inventory, marked, UI.ruleForm?.id);
    indicator.textContent = catalogInventoryStatus(inventory);
    syncCatalogCategories(form);
  } catch (error) {
    if (form.isConnected) indicator.textContent = error.message;
  } finally { button.disabled = false; }
}

function normalizeSearch(value) {
  return String(value || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();
}

function rulePorts(rule) {
  const project = S.config.projects?.find(item => item.id === rule.project_id);
  const sources = rule.sources || [];
  return { origins: rule.sourceMode === 'scoped' || sources.length ? sources : S.config.watch_dirs,
    destination: project?.directory || rule.destination };
}

function ruleSentence(rule) {
  const { origins, destination } = rulePorts(rule);
  const criteria = rule.conditions || {};
  const types = criteria.extensions?.length ? criteria.extensions.slice(0, 6).join(', ') + (criteria.extensions.length > 6 ? ' e outros selecionados' : '') :
    criteria.categories?.length ? criteria.categories.join(', ') : Object.values(criteria).some(value => Array.isArray(value) ? value.length : value !== '' && value != null) ? 'os critérios definidos' : 'tipos ainda por escolher';
  const source = origins.length ? origins.map(pathName).join(', ') : 'uma origem a escolher';
  return `Arquivos que correspondem a ${types} em ${source} serão movidos para ${destination ? pathName(destination) : 'um destino a escolher'}.`;
}

function updateRuleSentence(form) {
  const f = new FormData(form);
  const subfolder = String(f.get('subfolder') || '').trim();
  const destination = String(f.get('destination') || '');
  const sourceMode = f.get('sourceMode');
  const draft = { ...UI.ruleForm, sourceMode, sources: sourceMode === 'scoped' ? f.getAll('sources') : [],
    project_id: f.get('project_id'), destination: subfolder && destination ? destination + '/' + subfolder : destination,
    conditions: { ...UI.ruleForm.conditions, extensions: [...f.getAll('ext'), ...extensionList(f.get('extensions_extra'))],
      categories: f.getAll('cat'), keywords: csv(f.get('keywords')) } };
  $('[data-rule-sentence]', form.closest('.wizard-layout')).textContent = ruleSentence(draft);
}

function ruleSourceOption({ mode, symbol, title, scope, subfolders, updates, example, checked }) {
  const id = `rule-source-${mode}`;
  return `<label class="source-option">
    <span class="source-option-header">
      <span class="source-option-icon">${icon(symbol)}</span>
      <strong id="${id}-title">${esc(title)}</strong>
      <input type="radio" name="sourceMode" value="${mode}" aria-labelledby="${id}-title" aria-describedby="${id}-scope" ${checked ? 'checked' : ''}>
    </span>
    <span class="source-option-details">
      <span id="${id}-scope" class="source-option-scope">${esc(scope)}</span>
      <span><b>Subpastas.</b> ${esc(subfolders)}</span>
      <span><b>Alterações futuras.</b> ${esc(updates)}</span>
    </span>
    <span class="source-option-example"><b>Exemplo</b><span>${esc(example)}</span></span>
  </label>`;
}

function ruleSourceStep(rule, canScope, scoped) {
  const monitored = S.config.watch_dirs;
  const specificOption = {
    mode: 'scoped', symbol: 'pasta', title: 'Pastas específicas',
    scope: 'Adicione uma ou mais pastas para esta regra procurar arquivos somente nelas.',
    subfolders: 'Você decide aqui se a regra também procura dentro das subpastas.',
    updates: 'A lista é salva nesta regra. Para trocar uma pasta, abra a regra e edite sua origem.',
    example: 'Procurar PDFs só em Projetos, mesmo com Downloads monitorada.',
    checked: scoped,
  };
  const monitoredOption = {
    mode: 'global', symbol: 'config', title: 'Pastas monitoradas',
    scope: 'Procura arquivos em todas as pastas da lista geral, em Configurações.',
    subfolders: 'Segue a opção “Incluir subpastas das origens gerais” das Configurações.',
    updates: 'Ao adicionar ou remover uma pasta em Configurações, esta regra usa a lista atualizada na próxima execução.',
    example: 'Se Downloads e Documentos estiverem na lista geral, a regra procura PDFs nas duas pastas.',
    checked: !scoped,
  };
  return `<h3 tabindex="-1">Origem da regra</h3>
    <p class="muted">Escolha onde o OrganizaLocal vai procurar arquivos. Você define quais mover e para onde na próxima etapa.</p>
    ${canScope ? `<fieldset class="source-options"><legend class="sr-only">Modo de seleção das pastas de origem</legend>
      ${ruleSourceOption(specificOption)}
      ${ruleSourceOption(monitoredOption)}
    </fieldset>` : ''}
    <div class="source-panel" data-scoped ${scoped ? '' : 'hidden'}>
      <h4>Pastas desta regra</h4>
      <p class="small muted">${supported('native_picker')
        ? 'Adicione pelo menos uma pasta. Use Escolher pasta ou cole o caminho completo e clique em Adicionar pasta.'
        : 'Adicione pelo menos uma pasta. Cole o caminho completo e clique em Adicionar pasta.'}</p>
      ${pathList('sources', 'Caminho da pasta', rule.sources || [])}
      ${monitored.length ? `<div class="row source-shortcuts"><span class="small muted">Adição rápida</span>${monitored.map(path => `<button type="button" data-act="rule-use-source" data-path="${esc(path)}" title="${esc(path)}">Adicionar ${esc(pathName(path))}</button>`).join('')}</div>` : ''}
      <label class="check source-recursive"><input type="checkbox" name="source_recursive" ${rule.source_recursive ? 'checked' : ''}>
        <span><strong>Incluir subpastas</strong><small>Marcado, procura também em pastas internas. Desmarcado, procura apenas nos arquivos diretamente dentro das origens.</small></span>
      </label>
    </div>
    <div class="source-panel" data-monitored ${scoped ? 'hidden' : ''}>
      <div class="spread">
        <h4>Pastas monitoradas hoje</h4>
        ${dashboardLink('config', 'Ver em Configurações', 'foldersSettings')}
      </div>
      ${monitored.length ? `<ul class="source-monitored-list">${monitored.map(path => `<li>${icon('pasta')}<span>${esc(path)}</span></li>`).join('')}</ul>` : '<p class="small muted">A lista está vazia. Adicione pastas em Configurações para a regra ter onde procurar.</p>'}
      <p class="small muted"><strong>Subpastas nas Configurações.</strong> ${S.config.recursive
        ? 'Ativadas. A busca entra também nas subpastas.'
        : 'Desativadas. A busca percorre os arquivos diretamente nas pastas da lista.'}</p>
    </div>`;
}

function ruleWizard() {
  const rule = UI.ruleForm;
  const { conditions: c = {} } = rule;
  const step = UI.ruleStep;
  const canScope = supported('rule_scope');
  const scoped = canScope && rule.sourceMode === 'scoped';
  const origins = rule.sources || [];
  const { destination } = rulePorts(rule);
  return `<div class="wizard-layout">
    <form class="card wizard" id="ruleForm" novalidate>
      <div class="wizard-heading"><h2>${rule.id ? 'Editar regra' : 'Criar regra de organização'}</h2><span class="small muted">Etapa ${step} de 3</span></div>
      ${wizardProgress(step, ['Origem', 'Tipos e destino', 'Revisão'])}
      <div class="notice err" data-form-error tabindex="-1" role="alert" hidden></div>
      <section class="wizard-step rule-source" ${step !== 1 ? 'hidden' : ''}>${ruleSourceStep(rule, canScope, scoped)}</section>
      <section class="wizard-step" ${step !== 2 ? 'hidden' : ''}><h3 tabindex="-1">Quais arquivos vão para onde?</h3>
        <label>Nome da regra<input name="name" value="${esc(rule.name || '')}" placeholder="Exemplo: PDFs de trabalho" maxlength="120"></label>
        <div class="wizard-types"><div class="spread"><h4>Tipos de arquivo</h4><button type="button" data-act="ext-scan" ${allowed('analyze') ? '' : 'disabled'}>Detectar tipos nas pastas</button></div>
          ${fieldHelp('Extensão é o final do nome do arquivo, como .jpg em foto.jpg. Marque um grupo inteiro ou selecione só os tipos que quer mover.')}
          <div class="type-filters"><label>Buscar extensão<input id="extFilter" type="search" placeholder="PDF, imagens, Excel…"></label>
            <label>Categoria<select id="extCategory" aria-controls="extPicker"></select></label>
            <label>Mostrar<select id="extMode"><option value="all">Todos os tipos</option><option value="found">Detectados nas pastas</option><option value="selected">Selecionados</option><option value="other">Outros formatos</option></select></label></div>
          <div class="spread type-status"><p data-selected-types role="status" class="small"></p>
            <p role="status" data-inventory-status class="small muted">${esc(catalogInventoryStatus(UI.extInv))}</p></div>
          <div id="extPicker" class="type-catalog">${catalogHtml(UI.extInv, new Set(c.extensions || []), rule.id)}</div>
          <p data-empty-types class="empty" hidden>Nenhum tipo corresponde a este filtro.</p></div>
        ${pathField({ label: 'Pasta de destino', name: 'destination', value: rule.destination })}
        <label>Nome de uma nova subpasta <small>Opcional. A pasta será criada na execução, se necessário.</small><input name="subfolder" value="${esc(rule.subfolderDraft || '')}" placeholder="Exemplo: PDFs"></label>
        ${ruleAdvancedHtml(rule)}
      </section>
      <section class="wizard-step" ${step !== 3 ? 'hidden' : ''}><h3 tabindex="-1">Confira e simule</h3>
        <dl class="wizard-summary"><dt>Origem</dt><dd>${esc((scoped ? origins : S.config.watch_dirs).join(' · ') || 'Nenhuma pasta configurada')}</dd>
          <dt>Destino</dt><dd>${esc(destination || 'Escolha um destino')}</dd>
          <dt>Critérios</dt><dd>${condChips(c) || 'Escolha pelo menos um tipo ou critério avançado'}</dd>
          <dt>Exceções</dt><dd>${rule.exceptions?.length || 0}</dd>
          <dt>Arquivos com mesmo nome</dt><dd>${esc(conflictLabel(S.config.conflict_policy))}</dd>
          <dt>Frequência ao ativar</dt><dd>${esc(scheduleText(S.config.organize_schedule))}</dd></dl>
        <div class="row"><button type="button" class="${UI.rulePreview ? '' : 'primary'}" data-act="rule-preview" ${canScope && allowed('analyze') ? '' : 'disabled'}>Simular esta regra</button><span class="small muted">A simulação só lê os arquivos e mostra o destino previsto.</span></div>
        ${!canScope ? '<p class="small muted">A simulação de rascunhos requer uma versão atualizada do serviço local.</p>' : ''}
        <div data-rule-preview>${rulePreviewHtml(UI.rulePreview)}</div>
      </section>
      <footer class="wizard-footer">
        <button type="button" data-act="rule-cancel">Cancelar</button>
        <div class="row">
          ${step > 1 ? '<button type="button" data-act="rule-back">Voltar</button>' : ''}
          ${step < 3 ? '<button type="button" class="primary" data-act="rule-next">Continuar</button>' :
            `<button type="submit">Salvar desativada</button><button type="button" class="${UI.rulePreview || !canScope || !allowed('analyze') ? 'primary' : ''}" data-act="rule-activate" ${canScope && allowed('analyze') && !UI.rulePreview ? 'disabled' : ''}>Salvar e ativar</button>`}
        </div>
      </footer>
    </form>
    <aside class="card rule-sentence"><span class="dashboard-icon">${icon('regras')}</span><h2>O que a regra fará</h2><p data-rule-sentence>${esc(ruleSentence(rule))}</p>
      ${fieldHelp('Se você preencher tipos, palavras e outros critérios, todos os grupos preenchidos precisam corresponder. Dentro de um grupo, basta uma extensão ou uma palavra selecionada.')}</aside>
  </div>`;
}

function conflictLabel(policy) {
  return { rename: 'Salvar com nome numerado', review: 'Enviar para revisão', skip: 'Manter o arquivo na origem' }[policy] || 'Conforme configurações';
}

function rulePreviewHtml(result) {
  if (!result) return '';
  const rows = result.rows.filter(item => item.destination || ['tie', 'other_rule', 'error', 'busy', 'exception'].includes(item.action)).slice(0, 6);
  const review = (result.summary.tie || 0) + (result.summary.suspicious || 0) + (result.policy === 'review' ? result.summary.conflict || 0 : 0);
  return `<div class="draft-result"><p role="status"><strong>${result.count} ${result.count === 1 ? 'analisado' : 'analisados'} · ${result.would_move} ${result.would_move === 1 ? 'seria movido' : 'seriam movidos'}</strong> · ${result.summary.no_match || 0} sem correspondência${review ? ` · ${review} para revisão` : ''}</p>
    ${(result.warnings || []).map(warning => `<p class="notice warn">${esc(warning)}. Se houver empate real, o arquivo vai para revisão.</p>`).join('')}
    ${rows.length ? `<ul class="draft-moves">${rows.map(item => `<li><strong>${esc(item.name)}</strong> <span>${esc(item.destination ? `Destino previsto: ${item.destination}` : item.reason || S.action_labels[item.action])}</span></li>`).join('')}</ul>` : '<p class="small muted">A simulação não encontrou destinos para mostrar. Revise as origens e os tipos escolhidos.</p>'}
  </div>`;
}

function stepRule(delta) {
  const form = $('#ruleForm');
  try {
    const rule = readRuleForm(form);
    if (delta > 0 && hasPendingPath(form)) throw new Error('Adicione a pasta digitada antes de continuar.');
    if (delta > 0 && UI.ruleStep === 1 && rule.sourceMode === 'scoped' && !rule.sources.length) throw new Error('Escolha uma pasta de origem para esta regra.');
    if (delta > 0 && UI.ruleStep === 2) {
      validateRuleDraft(rule);
      if (rule.subfolderDraft) {
        const separator = S.app.os === 'nt' ? '\\' : '/';
        rule.destination = rule.destination.replace(/[\\/]+$/, '') + separator + rule.subfolderDraft;
        rule.subfolderDraft = '';
      }
    }
    const oldScope = JSON.stringify([UI.ruleForm.sourceMode, UI.ruleForm.sources, UI.ruleForm.source_recursive]);
    const newScope = JSON.stringify([rule.sourceMode, rule.sources, rule.source_recursive]);
    if (oldScope !== newScope) UI.extInv = null;
    UI.ruleForm = rule;
    UI.ruleStep += delta;
    render();
    $('#ruleForm .wizard-step:not([hidden]) h3')?.focus();
    if (UI.ruleStep === 2 && !UI.extInv) refreshCatalog($('#ruleForm'));
  } catch (error) { formError(form, error.message); }
}

function validateRuleDraft(rule) {
  if (!rule.name.trim()) throw new Error('Dê um nome à regra antes de continuar.');
  if (!rule.destination && !rule.project_id) throw new Error('Escolha a pasta que vai receber os arquivos.');
  const absolute = path => /^(~[\\/])/.test(path) || (S.app.os === 'nt' ? /^(?:[a-z]:[\\/]|\\\\)/i.test(path) : path.startsWith('/'));
  if (rule.sources.some(path => !absolute(path))) throw new Error('Informe o caminho completo da pasta de origem.');
  if (rule.destination && !absolute(rule.destination)) throw new Error('Informe o caminho completo da pasta de destino.');
  if (!Object.values(rule.conditions).some(value => Array.isArray(value) ? value.length : value != null && value !== '')) {
    throw new Error('Marque um tipo de arquivo ou preencha um critério avançado.');
  }
  if (rule.conditions.extensions.some(ext => !/^\.[a-z0-9][a-z0-9.]{0,14}$/.test(ext))) {
    throw new Error('Use extensões como .pdf ou .tar.gz, separadas por vírgulas.');
  }
  if (!Number.isInteger(rule.priority) || rule.priority < 0 || rule.priority > 10) throw new Error('A prioridade deve ficar entre 0 e 10.');
  if (['size_min', 'size_max'].some(key => rule.conditions[key] !== null && !Number.isFinite(rule.conditions[key]))) throw new Error('Informe um tamanho numérico em MB.');
  if (rule.subfolderDraft && (!rule.destination || rule.project_id || /[<>:"/\\|?*]|[. ]$/.test(rule.subfolderDraft))) {
    throw new Error('Escolha uma pasta de destino e use um nome simples para a subpasta.');
  }
}

async function previewRule(button) {
  const form = button.closest('form');
  if (button.disabled) return;
  formError(form);
  button.disabled = true;
  button.textContent = 'Simulando…';
  try {
    const rule = readRuleForm(form);
    validateRuleDraft(rule);
    const result = await call('simulate_draft', { rule, id: rule.id });
    if (!form.isConnected) return;
    UI.rulePreview = result;
    $('[data-rule-preview]', form).innerHTML = rulePreviewHtml(result);
    const activate = $('[data-act=rule-activate]', form);
    activate.disabled = false;
    activate.classList.add('primary');
    button.classList.remove('primary');
  } catch (error) { if (form.isConnected) formError(form, error.message); }
  finally { button.textContent = 'Simular esta regra'; button.disabled = false; }
}

async function saveRuleDraft(form, enabled) {
  if (UI.savingRule || UI.ruleStep !== 3 || (enabled && supported('rule_scope') && allowed('analyze') && !UI.rulePreview)) return;
  formError(form);
  UI.savingRule = true;
  try {
    const rule = readRuleForm(form);
    validateRuleDraft(rule);
    if (enabled) {
      const confirm = await confirmBox({ title: 'Salvar e ativar a regra?',
        text: `<p>A regra <b>${esc(rule.name)}</b> será usada nas próximas organizações. Frequência atual: ${esc(scheduleText(S.config.organize_schedule))}.</p><p>Salvar não executa a organização.</p>`,
        okText: 'Salvar e ativar' });
      if (!confirm) return;
    }
    delete rule.sourceMode;
    delete rule.subfolderDraft;
    await call('rule_save', { id: rule.id, rule: { ...rule, enabled } });
    UI.ruleForm = null;
    UI.ruleDirty = false;
    UI.rulePreview = null;
    if (enabled) safeSet('ol_setup_dismissed', '1');
    toast(enabled ? 'Regra salva e ativada.' : 'Regra salva desativada.');
    await refresh();
  } catch (error) {
    if (form.isConnected) formError(form, error.message);
    else toast(error.message, true);
  } finally { UI.savingRule = false; }
}

async function beginRule(existing, ext = '', origin = '') {
  if (UI.ruleDirty && !await confirmBox({ title: 'Substituir o rascunho atual?', text: 'As alterações não salvas desta regra serão descartadas.', danger: true, okText: 'Substituir rascunho' })) return;
  UI.ruleForm = existing ? { ...structuredClone(existing), sourceMode: existing.sources?.length ? 'scoped' : 'global' } :
    { name: '', enabled: false, priority: 5, create_destination: true, sourceMode: supported('rule_scope') ? 'scoped' : 'global',
      sources: origin && supported('rule_scope') ? [origin] : [], conditions: { extensions: ext ? [ext] : [] }, exceptions: [] };
  UI.ruleStep = 1;
  UI.ruleDirty = false;
  UI.rulePreview = null;
  UI.extInv = null;
  TAB = 'regras';
  safeSet('ol_tab', TAB);
  render();
  $('#ruleForm .wizard-step:not([hidden]) h3')?.focus();
  window.scrollTo(0, 0);
}

async function cancelRule() {
  if (UI.ruleDirty && !await confirmBox({ title: 'Descartar o rascunho da regra?', text: 'As alterações não salvas serão perdidas.', danger: true, okText: 'Descartar rascunho' })) return;
  UI.ruleForm = null;
  UI.ruleDirty = false;
  UI.rulePreview = null;
  render();
}

async function toggleRule(data) {
  const rule = S.rules.find(item => item.id === data.id);
  const enabled = data.enabled === '1';
  if (enabled && !await confirmBox({ title: 'Ativar esta regra?',
    text: `<p>${esc(ruleSentence(rule))}</p><p>Frequência atual: ${esc(scheduleText(S.config.organize_schedule))}.</p>`, okText: 'Ativar regra' })) return;
  return run('rule_toggle', { id: rule.id, enabled }, { success: enabled ? 'Regra ativada.' : 'Regra desativada.' });
}

function ruleListItem(rule) {
  const { origins, destination } = rulePorts(rule);
  const hasProblem = S.problems.some(problem => problem.rule_id === rule.id || problem.rule_ids?.includes(rule.id));
  return `<article class="card compact-rule" data-rule-state="${rule.enabled ? 'active' : 'inactive'}" data-rule-issue="${hasProblem}"
    data-search="${esc([rule.name, ...origins, destination, Object.values(rule.conditions || {}).flat().join(' ')].join(' '))}">
    <div class="compact-rule-content"><span class="dashboard-icon">${icon('regras')}</span><div>
      <div class="row"><strong>${esc(rule.name)}</strong>${badge(rule.enabled ? 'Ativa' : 'Inativa', rule.enabled ? 'ok' : '')}${hasProblem ? badge('Requer atenção', 'warn') : ''}</div>
      <p>${esc(ruleSentence(rule))}</p></div></div>
    <div class="row rule-list-actions">
      ${allowed('rules') ? (rule.enabled ? `<button data-act="rule-edit" data-id="${esc(rule.id)}">Editar</button>` :
        `<button data-act="toggle" data-id="${esc(rule.id)}" data-enabled="1">Ativar</button>`) : ''}
      <details class="action-menu"><summary>Mais</summary><div class="row">
        ${allowed('analyze') ? `<button data-act="rule-test" data-id="${esc(rule.id)}">Testar regra</button>` : ''}
        ${allowed('rules') ? `${rule.enabled ? `<button data-act="toggle" data-id="${esc(rule.id)}" data-enabled="0">Desativar</button>` :
          `<button data-act="rule-edit" data-id="${esc(rule.id)}">Editar regra</button>`}
          <button data-act="rule-dup" data-id="${esc(rule.id)}">Duplicar</button><button class="danger" data-act="rule-del" data-id="${esc(rule.id)}">Excluir regra</button>` : ''}
      </div></details>
    </div>
    <details class="rule-detail"><summary>Detalhes e prioridade ${rule.priority}</summary>
      <p><strong>Origem</strong> ${esc(origins.join(' · ') || 'Nenhuma pasta monitorada')}</p>
      <p><strong>Destino</strong> ${esc(destination || 'Conforme projeto')}</p>
      <div>${condChips(rule.conditions)}</div>
      ${rule.exceptions?.length ? `<ul>${rule.exceptions.map(e => `<li>${esc(e.description || Object.values(e.conditions).flat().join(', '))} · ${e.action === 'move' ? `Mover para ${esc(e.destination)}` : 'Ignorar'}</li>`).join('')}</ul>` : ''}
      ${allowed('rules') ? `<div class="row"><span class="small muted">O número maior tem preferência.</span>
        <button data-act="prio" data-id="${esc(rule.id)}" data-delta="-1" ${rule.priority <= 0 ? 'disabled' : ''}>Diminuir prioridade</button>
        <button data-act="prio" data-id="${esc(rule.id)}" data-delta="1" ${rule.priority >= 10 ? 'disabled' : ''}>Aumentar prioridade</button></div>` : ''}
    </details>
  </article>`;
}

function viewRegras() {
  if (UI.ruleForm) return header('Regras de organização', 'Origem, tipos de arquivo, destino e revisão.') + ruleWizard();
  const order = UI.ruleOrder || 'priority';
  const rules = order === 'name' ? [...S.rules].sort((a, b) => a.name.localeCompare(b.name, 'pt-BR')) : S.rules;
  const actions = allowed('rules') ? '<button class="primary" data-act="rule-new">Nova regra</button>' : '';
  return header('Regras de organização', 'Defina quais arquivos vão para cada pasta.', actions) +
    `<div class="card filter-bar">
      <label>Buscar regra<input id="ruleSearch" type="search" value="${esc(UI.ruleSearch || '')}" placeholder="Nome, pasta ou tipo de arquivo"></label>
      <label>Status<select id="ruleStatus">${[['all', 'Todas'], ['active', 'Ativas'], ['inactive', 'Inativas'], ['issue', 'Com problemas']].map(([key, label]) => `<option value="${key}"${selected(key, UI.ruleStatus || 'all')}>${label}</option>`).join('')}</select></label>
      <label>Ordenar por<select id="ruleOrder"><option value="priority"${selected('priority', order)}>Prioridade</option><option value="name"${selected('name', order)}>Nome</option></select></label>
      ${allowed('analyze') ? '<button data-act="validate">Validar regras</button>' : ''}
    </div>
    ${S.problems.length ? `<details class="card"><summary>Problemas e possíveis empates (${S.problems.length})</summary><ul>${S.problems.map(problem => `<li><strong>${esc(problem.rule)}</strong> · ${esc(problem.error)}</li>`).join('')}</ul></details>` : ''}
    <div class="grid compact-rule-list">${rules.map(ruleListItem).join('')}</div>
    <div id="emptyRules" class="card">${empty(rules.length ? 'Nenhuma regra corresponde à busca ou ao filtro.' : 'Comece escolhendo de onde vêm os arquivos e para onde devem ir.')}${!rules.length ? actions : ''}</div>`;
}

function filterRules() {
  const query = normalizeSearch(UI.ruleSearch);
  const status = UI.ruleStatus || 'all';
  let visible = 0;
  $$('.compact-rule').forEach(card => {
    card.hidden = !normalizeSearch(card.dataset.search).includes(query) ||
      (status !== 'all' && (status === 'issue' ? card.dataset.ruleIssue !== 'true' : status !== card.dataset.ruleState));
    if (!card.hidden) visible += 1;
  });
  if ($('#emptyRules')) $('#emptyRules').hidden = visible !== 0;
}

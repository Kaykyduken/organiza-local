'use strict';
/* =============================================================================
   OrganizaLocal — interface web (JavaScript puro, sem frameworks)

   Esta página roda no navegador (publicada na Vercel ou servida localmente) e
   conversa com o programa Python do computador pela API http://127.0.0.1:8765.

   Organização deste arquivo:
     1. Conexão (token, pareamento, chamadas à API)
     2. Utilitários (escape de HTML, formatação, modal, toast)
     3. Telas: Painel, Regras, Organização, Backups, Histórico, Ferramentas,
        Segurança, Sistema e Configurações
     4. Ações (cliques) e inicialização
   ============================================================================= */

/* ---------------------------------------------------------------------------
   1. CONEXÃO
   --------------------------------------------------------------------------- */
const IS_LOCAL = ['127.0.0.1', 'localhost'].includes(location.hostname);
const hashParams = new URLSearchParams(location.hash.slice(1));
// O atalho do programa abre o site com #token=...&api=... ; guardamos e limpamos a URL.
if (hashParams.get('token')) {
  sessionStorage.setItem('ol_token', hashParams.get('token'));
  if (hashParams.get('api')) sessionStorage.setItem('ol_api', hashParams.get('api'));
  history.replaceState(null, '', location.pathname + location.search);
}
const API = IS_LOCAL ? location.origin : (sessionStorage.getItem('ol_api') || 'http://127.0.0.1:8765');
let TOKEN = sessionStorage.getItem('ol_token') || '';

let S = null;                                   // último estado recebido do programa
let TAB = safeGet('ol_tab') || 'painel';        // aba aberta
const UI = {                                    // estado só da interface
  ruleForm: null,        // regra em edição (objeto) ou null
  backupForm: null,      // regra de backup em edição
  simulation: null,      // resultado da última simulação (HU10)
  lastRun: null,         // resultado da última organização (HU12)
  history: null, historyFilters: {},
  sysinfo: null,
  tools: {},             // resultados das ferramentas
  simFilter: 'todos',
};

function safeGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
function safeSet(key, value) { try { localStorage.setItem(key, value); } catch { /* modo privado */ } }

/** Chama uma ação da API local. Lança erro com a mensagem do servidor. */
async function call(command, payload = {}) {
  let response;
  try {
    response = await fetch(`${API}/api/action/${command}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${TOKEN}` },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    setConnection(false);
    throw new Error('Não foi possível falar com o programa local. Ele está aberto?');
  }
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) { TOKEN = ''; sessionStorage.removeItem('ol_token'); renderPairing(); throw new Error(data.error || 'Não autorizado'); }
  if (!response.ok) throw new Error(data.error || `Erro ${response.status}`);
  return data.result;
}

async function ping() {
  try {
    const r = await fetch(`${API}/api/ping`, { cache: 'no-store' });
    return r.ok ? r.json() : null;
  } catch { return null; }
}

/** Baixa um relatório/exportação gerado pelo programa (precisa do token no cabeçalho). */
async function download(kind, filename) {
  const r = await fetch(`${API}/api/download/${kind}/${encodeURIComponent(filename)}`, { headers: { Authorization: `Bearer ${TOKEN}` } });
  if (!r.ok) return toast('Arquivo não encontrado.', true);
  saveBlob(await r.blob(), filename);
}
function saveBlob(blob, filename) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

function setConnection(ok, text) {
  const el = document.getElementById('connection');
  el.className = 'pill ' + (ok ? 'ok' : 'err');
  el.textContent = text || (ok ? '● Programa local conectado' : '● Programa local desconectado');
}

/** Recarrega o estado completo e redesenha a tela. */
async function refresh() {
  S = await call('state');
  document.body.className = S.config.theme || 'claro';
  setConnection(true, `● Conectado · ${S.app.platform} · perfil ${S.active_profile}`);
  document.getElementById('navfoot').innerHTML = `Arquivos processados só no seu computador.<br>v${esc(S.app.version)} · ${IS_LOCAL ? 'interface local' : 'site publicado'}`;
  render();
}

/* ---------------------------------------------------------------------------
   2. UTILITÁRIOS
   --------------------------------------------------------------------------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Escapa texto antes de colocar no HTML (evita injeção de HTML por nomes de arquivos). */
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function bytes(n) {
  n = Number(n || 0);
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0).replace('.', ',')} ${units[i]}`;
}
function when(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d) ? esc(iso) : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}
const lines = text => String(text || '').split(/\r?\n/).map(s => s.trim()).filter(Boolean);
const csv = text => String(text || '').split(',').map(s => s.trim()).filter(Boolean);
const badge = (text, kind = '') => `<span class="badge ${kind}">${esc(text)}</span>`;
const empty = text => `<div class="empty">${esc(text)}</div>`;

const STATUS_BADGE = { ok: 'ok', partial: 'warn', error: 'err', pending: 'warn', unchanged: 'info', detected: 'warn' };
const STATUS_TEXT = { ok: 'sucesso', partial: 'parcial', error: 'falhou', pending: 'pendente', unchanged: 'sem mudanças', detected: 'detectado' };
const OPS = {
  move: 'Movido', quarantine: 'Quarentena', organize: 'Organização', backup: 'Backup', restore: 'Restauração',
  undo: 'Desfeito', review: 'Revisão', review_decision: 'Decisão de revisão', rename: 'Renomeado',
  rule_save: 'Regra salva', rule_delete: 'Regra excluída', rule_toggle: 'Regra ativada/desativada',
  rule_priority: 'Prioridade', config_save: 'Configuração', external_change: 'Alteração externa',
  backup_retention: 'Retenção de backup', backup_lock: 'Versão travada', backup_verify: 'Verificação de backup',
  service_start: 'Serviço iniciado', service_stop: 'Serviço encerrado', install: 'Instalação', report: 'Relatório',
  duplicate_remove: 'Duplicado apagado', sandbox: 'Sandbox', extract: 'Extração', archive_inspect: 'Inspeção',
  pair: 'Pareamento', quarantine_release: 'Liberado da quarentena', quarantine_delete: 'Apagado da quarentena',
  backup_job_save: 'Regra de backup salva', backup_job_delete: 'Regra de backup excluída', config_restore: 'Config. restaurada',
  config_import: 'Config. importada', profile_switch: 'Troca de perfil', scheduler: 'Agendador', api_error: 'Erro da API',
};
const statusBadge = s => badge(STATUS_TEXT[s] || s, STATUS_BADGE[s] || '');
const ACTION_KIND = { suspicious: 'err', move: 'ok', default: 'ok', quarantine: 'err', exception: 'info', tie: 'warn', conflict: 'warn', no_match: '', busy: '', excluded: '', already: '', error: 'err' };

function toast(message, isError = false) {
  const el = document.createElement('div');
  el.textContent = message;
  if (isError) el.className = 'err';
  $('#toast').appendChild(el);
  setTimeout(() => el.remove(), isError ? 7000 : 3500);
}

/** Janela de confirmação. options.password=true pede a senha crítica (se configurada). */
function confirmBox({ title, text = '', okText = 'Confirmar', danger = false, password = false, fields = '' }) {
  return new Promise(resolve => {
    const needsPass = password && S?.config?.critical_password_enabled;
    const modal = $('#modal');
    modal.innerHTML = `<form class="box">
        <h2>${esc(title)}</h2><div>${text}</div>${fields}
        ${needsPass ? '<label>Senha de operações críticas<input type="password" name="password" required autocomplete="current-password"></label>' : ''}
        <div class="row" style="justify-content:flex-end"><button type="button" data-close>Cancelar</button>
        <button class="${danger ? 'danger' : 'primary'}" type="submit">${esc(okText)}</button></div></form>`;
    modal.classList.remove('hidden');
    const form = $('form', modal);
    const close = value => { modal.classList.add('hidden'); modal.innerHTML = ''; resolve(value); };
    $('[data-close]', modal).onclick = () => close(null);
    form.onsubmit = e => { e.preventDefault(); close(Object.fromEntries(new FormData(form))); };
    (form.querySelector('input, select, textarea') || form.querySelector('button[type=submit]')).focus();
  });
}
function showModal(title, html, wide = true) {
  const modal = $('#modal');
  modal.innerHTML = `<div class="box ${wide ? 'wide' : ''}"><div class="spread"><h2>${esc(title)}</h2><button data-close>Fechar</button></div>${html}</div>`;
  modal.classList.remove('hidden');
  $('[data-close]', modal).onclick = () => { modal.classList.add('hidden'); modal.innerHTML = ''; };
}

/** Executa uma ação mostrando erro amigável e, opcionalmente, recarregando o estado. */
async function run(command, payload, { success, reload = true } = {}) {
  try {
    const result = await call(command, payload);
    if (success) toast(typeof success === 'function' ? success(result) : success);
    if (reload) await refresh();
    return result;
  } catch (err) {
    toast(err.message, true);
    return undefined;
  }
}

/* ---------------------------------------------------------------------------
   3. TELAS
   --------------------------------------------------------------------------- */
function header(title, subtitle, extra = '') {
  return `<div class="spread"><div><h1>${esc(title)}</h1><p class="subtitle">${subtitle}</p></div><div class="row">${extra}</div></div>`;
}
function bars(data, max = 8) {
  const entries = Object.entries(data || {}).slice(0, max);
  if (!entries.length) return empty('Sem dados ainda.');
  const top = Math.max(...entries.map(e => e[1]));
  return `<div class="bars">${entries.map(([k, v]) => `<div class="bar"><span title="${esc(k)}">${esc(k)}</span><div><i style="width:${(100 * v / top).toFixed(0)}%"></i></div><b>${v}</b></div>`).join('')}</div>`;
}
function scheduleText(sch) {
  if (!sch || sch.frequency === 'off') return 'Desligada';
  if (sch.frequency === 'interval') return `A cada ${sch.interval_minutes} minutos`;
  const days = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo'];
  return sch.frequency === 'daily' ? `Todos os dias às ${sch.time}` : `Toda ${days[sch.weekday]} às ${sch.time}`;
}
function eventRow(e, withActions = false) {
  const canUndo = withActions && ['move', 'review', 'rename'].includes(e.operation) && e.status === 'ok';
  return `<tr><td class="small">${when(e.timestamp)}</td><td>${esc(OPS[e.operation] || e.operation)}</td><td>${statusBadge(e.status)}</td>
    <td class="path small">${e.source ? esc(e.source) : esc(e.detail || '')}${e.destination ? `<br><span class="muted">→ ${esc(e.destination)}</span>` : ''}
    ${e.reason ? `<br><span class="muted">Motivo: ${esc(e.reason)}</span>` : ''}${e.operation === 'organize' ? `<br><span class="muted">${e.moved} movidos · ${e.reviewed} revisão · ${e.failures || 0} falhas · gatilho ${esc(e.trigger || '')}</span>` : ''}</td>
    <td class="small">${esc(e.rule_name || '')}</td>
    ${withActions ? `<td><div class="row">${canUndo ? `<button class="icon" data-act="undo" data-id="${e.id}">Desfazer</button>` : ''}<button class="icon ghost" data-act="note-for" data-type="operation" data-ref="${e.id}">Obs.</button></div></td>` : ''}</tr>`;
}

/* ----- Painel ----- */
function viewPainel() {
  const st = S.stats, sch = S.scheduler;
  const active = S.rules.filter(r => r.enabled).length;
  const alerts = [
    ...S.problems.map(p => `<div class="notice warn"><b>${esc(p.rule)}:</b> ${esc(p.error)}</div>`),
    ...S.alerts.map(a => `<div class="notice err">Limite ${esc(a.severity)}: ${esc(a.path || a.category)} — ${bytes(a.bytes)} de ${bytes(a.max_bytes)}</div>`),
    ...S.due_documents.map(d => `<div class="notice ${d.days_remaining < 0 ? 'err' : 'warn'}">Vencimento: ${esc(d.description || d.file)} — ${d.days_remaining < 0 ? `venceu há ${-d.days_remaining} dia(s)` : `em ${d.days_remaining} dia(s)`}</div>`),
  ];
  if (!active) alerts.unshift('<div class="notice">Nenhuma regra ativa. As regras de exemplo vêm <b>desativadas</b>: revise-as na aba Regras e ative as que quiser.</div>');
  return `${header('Painel', 'Resumo da organização automática e dos backups.')}
  <div class="grid g4">
    <div class="card stat"><small>Arquivos organizados</small><b>${st.moves}</b><small>${bytes(st.moved_bytes)} movidos</small></div>
    <div class="card stat"><small>Regras ativas</small><b>${active} / ${S.rules.length}</b><small>${S.problems.length} aviso(s)</small></div>
    <div class="card stat"><small>Versões de backup</small><b>${st.backup_versions}</b><small>${bytes(st.backup_bytes)} em disco</small></div>
    <div class="card stat"><small>Aguardando revisão</small><b>${st.pending_review}</b><small>${S.quarantine.length} na quarentena</small></div>
  </div>
  <div class="grid g2">
    <div class="card"><h2>Situação</h2>
      <p><b>Pastas monitoradas:</b><br>${S.config.watch_dirs.map(d => `<code>${esc(d)}</code>`).join('<br>') || '<span class="muted">nenhuma</span>'}</p>
      <p><b>Organização automática:</b> ${esc(scheduleText(S.config.organize_schedule))}<br>
      <b>Última:</b> ${when(sch.last_organize)} · <b>Próxima:</b> ${when(sch.next_organize)}</p>
      <p><b>Backups:</b> ${S.backup_jobs.length ? S.backup_jobs.map(j => `${esc(j.name)} (${j.versions.length}/${j.max_versions} versões)`).join(', ') : 'nenhuma regra de backup'}</p>
      <div class="row"><button class="primary" data-act="simulate-go">Simular organização</button><button data-act="organize">Organizar agora</button></div>
    </div>
    <div class="card"><h2>Alertas e avisos</h2>${alerts.join('') || empty('Tudo certo por aqui.')}</div>
  </div>
  <div class="grid g2">
    <div class="card"><h2>Organizados por categoria</h2>${bars(st.by_category)}</div>
    <div class="card"><h2>Organizados por regra</h2>${bars(st.by_rule)}</div>
  </div>
  <div class="card"><div class="spread"><h2>Atividade recente</h2><button data-tab-go="historico">Ver histórico completo</button></div>
    ${S.latest.length ? `<div class="table-wrap"><table><thead><tr><th>Data</th><th>Operação</th><th>Status</th><th>Arquivo / detalhe</th><th>Regra</th></tr></thead><tbody>${S.latest.slice(0, 12).map(e => eventRow(e)).join('')}</tbody></table></div>` : empty('Nenhuma atividade registrada.')}
  </div>`;
}

/* ----- Regras (HU01–HU09) ----- */
const COND_LABELS = { extensions: 'Extensão', keywords: 'Palavra no nome', categories: 'Categoria', formats: 'Formato real', prefix: 'Começa com', suffix: 'Termina com', glob: 'Padrão', regex: 'Regex', size_min: 'Mín.', size_max: 'Máx.', modified_after: 'Modificado após', modified_before: 'Modificado antes', age_days_min: 'Idade mín. (dias)', age_days_max: 'Idade máx. (dias)' };
function condChips(conditions) {
  return Object.entries(conditions || {}).map(([k, v]) => {
    let value = Array.isArray(v) ? v.join(', ') : v;
    if (k === 'formats') value = v.map(f => S.format_labels[f] || f).join(', ');
    if (k === 'size_min' || k === 'size_max') value = bytes(v);
    return `<span class="cond"><b>${esc(COND_LABELS[k] || k)}:</b> ${esc(value)}</span>`;
  }).join('');
}
function viewRegras() {
  const form = UI.ruleForm ? ruleFormHtml(UI.ruleForm) : '';
  const list = S.rules.length ? S.rules.map(r => {
    const tie = S.rules.some(o => o.id !== r.id && o.enabled && r.enabled && o.priority === r.priority);
    return `<div class="rule ${r.enabled ? '' : 'off'}">
      <div class="prio"><button class="icon" title="Aumentar prioridade" data-act="prio" data-id="${r.id}" data-delta="1" ${r.priority >= 10 ? 'disabled' : ''}>▲</button><b>${r.priority}</b><button class="icon" title="Diminuir prioridade" data-act="prio" data-id="${r.id}" data-delta="-1" ${r.priority <= 0 ? 'disabled' : ''}>▼</button></div>
      <div><div class="row"><strong>${esc(r.name)}</strong>${r.enabled ? badge('Ativa', 'ok') : badge('Inativa')}
        ${r.exceptions.length ? badge(`${r.exceptions.length} exceção(ões)`, 'info') : badge('sem exceções')}${tie ? badge('mesma prioridade de outra regra', 'warn') : ''}</div>
        <div>${condChips(r.conditions)}</div>
        <div class="small muted">Destino: <code>${esc(r.destination)}</code>${r.rename_pattern ? ` · renomear: <code>${esc(r.rename_pattern)}</code>` : ''}</div>
        ${r.exceptions.length ? `<div class="small muted">Exceções: ${r.exceptions.map(x => `${esc(x.description || Object.values(x.conditions).flat().join(', '))} (${x.action === 'skip' ? 'não mover' : 'mover para ' + esc(x.destination)})`).join('; ')}</div>` : ''}
      </div>
      <div class="actions"><button data-act="toggle" data-id="${r.id}" data-enabled="${r.enabled ? 0 : 1}">${r.enabled ? 'Desativar' : 'Ativar'}</button>
        <button data-act="rule-edit" data-id="${r.id}">Editar</button><button data-act="rule-test" data-id="${r.id}">Testar</button>
        <button data-act="rule-dup" data-id="${r.id}">Duplicar</button><button class="danger" data-act="rule-del" data-id="${r.id}">Excluir</button></div></div>`;
  }).join('') : empty('Nenhuma regra cadastrada. Clique em "Nova regra".');
  return `${header('Regras de organização', 'Ordenadas por prioridade (0 a 10). Quando um arquivo atende a mais de uma regra, vale a de maior prioridade; empates vão para a fila de revisão.', '<button class="primary" data-act="rule-new">+ Nova regra</button><button data-act="validate">Validar regras</button>')}
  ${form}
  ${S.problems.length ? `<div class="card">${S.problems.map(p => `<div class="notice warn small"><b>${esc(p.rule)}:</b> ${esc(p.error)}</div>`).join('')}</div>` : ''}
  <div class="grid">${list}</div>`;
}
function excRowHtml(x = {}) {
  const kind = Object.keys(x.conditions || {})[0] || 'keywords';
  const value = [].concat((x.conditions || {})[kind] || []).join(', ');
  const kinds = ['keywords', 'extensions', 'categories', 'prefix', 'suffix', 'glob', 'regex'];
  return `<div class="form exc-row" style="grid-template-columns:1.2fr 1.6fr 1.2fr 1.8fr 1.6fr auto;align-items:end">
    <label>Condição<select name="kind">${kinds.map(k => `<option value="${k}" ${k === kind ? 'selected' : ''}>${COND_LABELS[k]}</option>`).join('')}</select></label>
    <label>Valor<input name="value" value="${esc(value)}" placeholder="ex.: boleto, rascunho"></label>
    <label>Ação<select name="action"><option value="skip" ${x.action !== 'move' ? 'selected' : ''}>Não mover</option><option value="move" ${x.action === 'move' ? 'selected' : ''}>Mover para outra pasta</option></select></label>
    <label>Pasta (se mover)<input name="destination" value="${esc(x.destination || '')}"></label>
    <label>Descrição<input name="description" value="${esc(x.description || '')}"></label>
    <button type="button" class="danger icon" data-act="exc-remove">✕</button></div>`;
}
function ruleFormHtml(r) {
  const c = r.conditions || {};
  const allCats = [...Object.keys(S.categories_builtin), ...Object.keys(S.config.categories || {})];
  const formats = Object.keys(S.format_labels).filter(f => !['texto', 'binario'].includes(f)).concat(['texto']);
  const mb = v => (v === null || v === undefined || v === '') ? '' : (v / 1048576).toString().replace('.', ',');
  return `<form class="card" id="ruleForm"><h2>${r.id ? 'Editar regra' : 'Nova regra'}</h2>
    <div class="form">
      <label class="two">Nome da regra<input name="name" required value="${esc(r.name || '')}" placeholder="ex.: Trabalhos da faculdade"></label>
      <label>Prioridade (0 a 10)<input name="priority" type="number" min="0" max="10" value="${r.priority ?? 5}"></label>
      <label class="two">Extensões (HU01) — separadas por vírgula<input name="extensions" value="${esc((c.extensions || []).join(', '))}" placeholder=".pdf, .docx, .xlsx"></label>
      <label>Palavras no nome (HU02)<input name="keywords" value="${esc((c.keywords || []).join(', '))}" placeholder="faculdade, fatec"></label>
      <label class="two">Pasta de destino (caminho completo)<input name="destination" required value="${esc(r.destination || '')}" placeholder="${S.app.os === 'nt' ? 'C:\\Users\\voce\\Documents\\Faculdade' : '/home/voce/Documentos/Faculdade'}"></label>
      <label>Projeto (opcional)<select name="project_id"><option value="">—</option>${(S.config.projects || []).map(p => `<option value="${esc(p.id)}" ${p.id === r.project_id ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></label>
      <label class="check"><input type="checkbox" name="create_destination" ${r.create_destination !== false ? 'checked' : ''}> Criar a pasta de destino se não existir</label>
      <label class="check"><input type="checkbox" name="enabled" ${r.enabled !== false ? 'checked' : ''}> Regra ativa</label>
    </div>
    <details style="margin-top:12px"><summary>Condições avançadas (categoria, formato real, tamanho, datas, padrões)</summary>
      <div class="form" style="margin-top:10px">
        <div class="full"><span class="small muted">Categorias</span><div class="row">${allCats.map(k => `<label class="check"><input type="checkbox" name="cat" value="${esc(k)}" ${(c.categories || []).includes(k) ? 'checked' : ''}> ${esc(k)}</label>`).join('')}</div></div>
        <div class="full"><span class="small muted">Formato real do conteúdo (lido dos primeiros bytes do arquivo)</span><div class="row">${formats.map(f => `<label class="check"><input type="checkbox" name="fmt" value="${f}" ${(c.formats || []).includes(f) ? 'checked' : ''}> ${esc(S.format_labels[f] || f)}</label>`).join('')}</div></div>
        <label>Nome começa com<input name="prefix" value="${esc(c.prefix || '')}"></label>
        <label>Nome termina com<input name="suffix" value="${esc(c.suffix || '')}"></label>
        <label>Padrão (* e ?)<input name="glob" value="${esc(c.glob || '')}" placeholder="nota_fiscal_*.pdf"></label>
        <label>Expressão regular<input name="regex" value="${esc(c.regex || '')}" placeholder="^\\d{4}-\\d{2}"></label>
        <label>Tamanho mínimo (MB)<input name="size_min" value="${mb(c.size_min)}"></label>
        <label>Tamanho máximo (MB)<input name="size_max" value="${mb(c.size_max)}"></label>
        <label>Modificado após<input name="modified_after" type="date" value="${esc(c.modified_after || '')}"></label>
        <label>Modificado antes<input name="modified_before" type="date" value="${esc(c.modified_before || '')}"></label>
        <label>Mais antigo que (dias)<input name="age_days_min" type="number" min="0" value="${c.age_days_min ?? ''}"></label>
        <label>Mais novo que (dias)<input name="age_days_max" type="number" min="0" value="${c.age_days_max ?? ''}"></label>
        <label class="two">Renomear ao mover (opcional)<input name="rename_pattern" value="${esc(r.rename_pattern || '')}" placeholder="{date}_{name}.{ext}  — também {year} {month} {day} {timestamp} {seq}"></label>
      </div></details>
    <h3>Exceções (HU05) — verificadas antes de aplicar a regra</h3>
    <div id="excList">${(r.exceptions || []).map(excRowHtml).join('')}</div>
    <button type="button" data-act="exc-add">+ Adicionar exceção</button>
    <hr><div class="row"><button class="primary" type="submit">Salvar regra</button><button type="button" data-act="rule-cancel">Cancelar</button>
    <span class="small muted">As condições preenchidas precisam valer todas ao mesmo tempo (E).</span></div></form>`;
}
function readRuleForm(form) {
  const f = new FormData(form);
  const toBytes = v => v === '' || v === null ? null : Math.round(parseFloat(String(v).replace(',', '.')) * 1048576);
  const exceptions = $$('.exc-row', form).map(row => {
    const get = n => $(`[name=${n}]`, row).value.trim();
    const kind = get('kind');
    const value = ['keywords', 'extensions', 'categories'].includes(kind) ? csv(get('value')) : get('value');
    return { conditions: { [kind]: value }, action: get('action'), destination: get('destination'), description: get('description') };
  }).filter(x => [].concat(Object.values(x.conditions)[0]).length && Object.values(x.conditions)[0] !== '');
  return {
    name: f.get('name'), priority: Number(f.get('priority')), destination: f.get('destination').trim(),
    project_id: f.get('project_id'), create_destination: f.has('create_destination'), enabled: f.has('enabled'),
    rename_pattern: f.get('rename_pattern') || '',
    conditions: {
      extensions: csv(f.get('extensions')), keywords: csv(f.get('keywords')), categories: f.getAll('cat'), formats: f.getAll('fmt'),
      prefix: f.get('prefix'), suffix: f.get('suffix'), glob: f.get('glob'), regex: f.get('regex'),
      size_min: toBytes(f.get('size_min')), size_max: toBytes(f.get('size_max')),
      modified_after: f.get('modified_after'), modified_before: f.get('modified_before'),
      age_days_min: f.get('age_days_min') === '' ? null : Number(f.get('age_days_min')),
      age_days_max: f.get('age_days_max') === '' ? null : Number(f.get('age_days_max')),
    },
    exceptions,
  };
}

/* ----- Organização (HU10–HU12) ----- */
function viewOrganizacao() {
  const sim = UI.simulation, res = UI.lastRun;
  const filters = ['todos', 'move', 'conflict', 'exception', 'tie', 'suspicious', 'quarantine', 'no_match', 'busy'];
  const rows = sim ? sim.rows.filter(r => UI.simFilter === 'todos' || r.action === UI.simFilter || (UI.simFilter === 'move' && r.action === 'default')) : [];
  const policy = { rename: 'salvar com nome numerado', review: 'enviar para revisão', skip: 'ignorar' }[S.config.conflict_policy];
  const simHtml = sim ? `<div class="card"><div class="spread"><h2>Simulação ${sim.only_rule_name ? `da regra "${esc(sim.only_rule_name)}"` : ''} — ${when(sim.timestamp)}</h2>
      <div class="row"><select id="simFilter">${filters.map(f => `<option value="${f}" ${f === UI.simFilter ? 'selected' : ''}>${f === 'todos' ? 'Todos' : esc(S.action_labels[f])}</option>`).join('')}</select><button data-act="sim-export">Exportar JSON</button></div></div>
      <p class="notice">Nada foi movido. ${sim.count} arquivo(s) analisado(s); <b>${sim.would_move}</b> seriam movidos. ${Object.entries(sim.summary).filter(([, v]) => v).map(([k, v]) => badge(`${S.action_labels[k]}: ${v}`, ACTION_KIND[k])).join(' ')}</p>
      ${rows.length ? `<div class="table-wrap"><table><thead><tr><th>Arquivo</th><th>Resultado previsto</th><th>Regra</th><th>Destino previsto</th><th>Observação</th></tr></thead><tbody>
      ${rows.map(r => `<tr><td class="path">${esc(r.name)}<br><span class="small muted">${esc(S.format_labels[r.format] || r.format || '')} · ${bytes(r.bytes)}</span></td><td>${badge(S.action_labels[r.action] || r.action, ACTION_KIND[r.action])}</td>
        <td>${esc(r.rule_name || '')}${r.matched && r.matched.length > 1 ? `<br><span class="small muted">correspondem: ${r.matched.map(m => `${esc(m.name)} (${m.priority})`).join(', ')}</span>` : ''}</td>
        <td class="path small">${esc(r.destination || '')}</td><td class="small">${esc(r.reason || '')}</td></tr>`).join('')}</tbody></table></div>` : empty('Nenhum arquivo neste filtro.')}</div>` : '';
  const resHtml = res ? `<div class="card"><div class="spread"><h2>Resultado da organização — ${when(res.finished)}</h2>${statusBadge(res.status)}</div>
      <div class="grid g4"><div class="stat"><small>Movidos</small><b>${res.moved}</b></div><div class="stat"><small>Para revisão</small><b>${res.reviewed}</b></div>
      <div class="stat"><small>Falhas</small><b style="color:${res.errors.length ? 'var(--err)' : 'inherit'}">${res.errors.length}</b></div><div class="stat"><small>Ignorados / quarentena</small><b>${res.skipped} / ${res.quarantined}</b></div></div>
      ${res.errors.length ? `<h3>Arquivos que não puderam ser movidos</h3><div class="table-wrap"><table><thead><tr><th>Arquivo</th><th>Motivo</th></tr></thead><tbody>${res.errors.map(e => `<tr><td class="path">${esc(e.file)}</td><td>${esc(e.reason)}</td></tr>`).join('')}</tbody></table></div>` : ''}
      ${res.moves.length ? `<h3>Arquivos organizados</h3><div class="table-wrap"><table><thead><tr><th>Origem</th><th>Destino</th><th>Regra</th><th>Método</th></tr></thead><tbody>${res.moves.map(m => `<tr><td class="path small">${esc(m.source)}</td><td class="path small">${esc(m.destination)}</td><td>${esc(m.rule_name || '—')}</td><td class="small">${esc(m.method)}</td></tr>`).join('')}</tbody></table></div>` : ''}</div>` : '';
  const review = S.review.length ? `<div class="table-wrap"><table><thead><tr><th>Arquivo</th><th>Motivo</th><th>Destino sugerido</th><th>Decisão</th></tr></thead><tbody>
    ${S.review.map(r => `<tr><td class="path">${esc(r.source)}</td><td>${esc(r.detail || r.reason)}</td><td class="path small">${esc(r.destination || '—')}</td>
    <td><div class="row">${r.destination ? `<button class="icon" data-act="rev" data-id="${r.id}" data-d="rename">Mover com novo nome</button><button class="icon danger" data-act="rev" data-id="${r.id}" data-d="replace">Substituir</button>` : ''}
    <button class="icon" data-act="rev" data-id="${r.id}" data-d="move">Escolher pasta…</button><button class="icon" data-act="rev" data-id="${r.id}" data-d="quarantine">Quarentena</button><button class="icon ghost" data-act="rev" data-id="${r.id}" data-d="ignore">Ignorar</button></div></td></tr>`).join('')}</tbody></table></div>` : empty('Nenhum arquivo aguardando decisão.');
  return `${header('Organização', `Pastas: ${S.config.watch_dirs.map(esc).join(', ') || 'nenhuma'} · Arquivo já existente no destino: <b>${esc(policy)}</b> (altere em Configurações).`,
    '<button class="primary" data-act="simulate">Simular (não move nada)</button><button data-act="organize">Organizar agora</button>')}
    ${resHtml}${simHtml}
    ${!sim && !res ? '<div class="card"><p>Use <b>Simular</b> para ver, sem mover nada, quais arquivos correspondem às regras e para onde iriam. Depois clique em <b>Organizar agora</b> — ou espere a organização automática.</p></div>' : ''}
    <div class="card"><h2>Fila de revisão (${S.review.length})</h2><p class="small muted">Arquivos com empate de prioridade ou com nome já existente no destino (quando a política é "revisão").</p>${review}</div>`;
}

/* ----- Backups ----- */
function viewBackups() {
  const form = UI.backupForm ? backupFormHtml(UI.backupForm) : '';
  const jobs = S.backup_jobs.length ? S.backup_jobs.map(j => {
    const used = j.versions.length;
    const vers = j.versions.slice().reverse();
    return `<div class="card"><div class="spread"><div><div class="row"><h2 style="margin:0">${esc(j.name)}</h2>${j.enabled ? badge('ativo', 'ok') : badge('desativado')}${badge(j.mode === 'zip' ? 'ZIP compactado' : 'cópia de pastas', 'info')}</div>
        <div class="small muted">A cada ${String(j.interval_hours).replace('.', ',')} h · próxima: ${j.next_run && j.next_run.includes('T') ? when(j.next_run) : esc(j.next_run || '—')} · última: ${when(j.last_run)}</div></div>
        <div class="row"><button class="primary" data-act="bk-run" data-id="${j.id}">Fazer backup agora</button><button data-act="bk-edit" data-id="${j.id}">Editar</button><button data-act="bk-open" data-id="${j.id}">Abrir pasta</button><button class="danger" data-act="bk-del" data-id="${j.id}">Excluir</button></div></div>
      <p class="small"><b>Origens:</b> ${j.sources.map(s => `<code>${esc(s)}</code>`).join(' ')}<br><b>Guardado em:</b> <code>${esc(j.folder)}</code>
      ${j.include_extensions.length ? `<br><b>Somente:</b> ${esc(j.include_extensions.join(', '))}` : ''}${j.exclude_patterns.length ? `<br><b>Ignorar:</b> ${esc(j.exclude_patterns.join(', '))}` : ''}</p>
      <div class="spread"><b>Versões: ${used} de no máximo ${j.max_versions}</b><span class="small muted">Versões travadas 🔒 nunca são apagadas automaticamente.</span></div>
      <div class="meter" style="margin:6px 0 10px"><i style="width:${Math.min(100, 100 * used / j.max_versions)}%"></i></div>
      ${vers.length ? `<div class="table-wrap"><table><thead><tr><th>Versão</th><th>Data</th><th>Arquivos</th><th>Tamanho</th><th>Gatilho</th><th>Ações</th></tr></thead><tbody>
      ${vers.map(v => `<tr><td class="mono">${v.locked ? '🔒 ' : ''}${esc(v.id)}</td><td>${when(v.timestamp)}</td><td>${v.files}</td><td>${bytes(v.bytes)}${v.mode === 'zip' ? `<br><span class="small muted">${bytes(v.stored_bytes)} compactado</span>` : ''}</td><td class="small">${esc(v.trigger || '')}</td>
        <td><div class="row"><button class="icon" data-act="bk-restore" data-job="${j.id}" data-v="${v.id}">Restaurar</button><button class="icon" data-act="bk-files" data-job="${j.id}" data-v="${v.id}">Arquivos</button>
        <button class="icon" data-act="bk-verify" data-job="${j.id}" data-v="${v.id}">Verificar</button><button class="icon" data-act="bk-lock" data-job="${j.id}" data-v="${v.id}" data-locked="${v.locked ? 0 : 1}">${v.locked ? 'Destravar' : 'Travar'}</button>
        <button class="icon danger" data-act="bk-vdel" data-job="${j.id}" data-v="${v.id}" ${v.locked ? 'disabled' : ''}>Apagar</button></div></td></tr>`).join('')}</tbody></table></div>
      ${vers.length > 1 ? `<div class="row" style="margin-top:10px"><span class="small">Comparar</span><select id="cmpA-${j.id}">${vers.map((v, i) => `<option ${i === 1 ? 'selected' : ''}>${esc(v.id)}</option>`).join('')}</select><span>com</span><select id="cmpB-${j.id}">${vers.map(v => `<option>${esc(v.id)}</option>`).join('')}</select><button data-act="bk-compare" data-job="${j.id}">Comparar versões</button></div>` : ''}`
      : empty('Nenhuma versão ainda. Clique em "Fazer backup agora".')}</div>`;
  }).join('') : '<div class="card">' + empty('Nenhuma regra de backup. Crie uma para proteger pastas importantes com várias versões.') + '</div>';
  return `${header('Backups', `Cada regra guarda até N versões (padrão ${S.config.default_max_versions}). Quando passa do limite, a versão mais antiga destravada é apagada.`, '<button class="primary" data-act="bk-new">+ Nova regra de backup</button><button data-act="bk-open">Abrir pasta de backups</button>')}
    ${form}${jobs}`;
}
function backupFormHtml(j) {
  return `<form class="card" id="backupForm"><h2>${j.id ? 'Editar regra de backup' : 'Nova regra de backup'}</h2><div class="form">
    <label class="two">Nome<input name="name" required value="${esc(j.name || '')}" placeholder="ex.: Trabalhos da faculdade"></label>
    <label>Formato<select name="mode"><option value="zip" ${j.mode !== 'copy' ? 'selected' : ''}>ZIP compactado</option><option value="copy" ${j.mode === 'copy' ? 'selected' : ''}>Cópia de pastas</option></select></label>
    <label class="full">Pastas ou arquivos de origem (um por linha)<textarea name="sources" required placeholder="${S.app.os === 'nt' ? 'C:\\Users\\voce\\Documents\\Faculdade' : '/home/voce/Documentos/Faculdade'}">${esc((j.sources || []).join('\n'))}</textarea></label>
    <label class="two">Destino (vazio = pasta de dados do aplicativo; pode ser um HD externo)<input name="destination" value="${esc(j.destination || '')}"></label>
    <label>Máximo de versões<input name="max_versions" type="number" min="1" max="100" value="${j.max_versions || S.config.default_max_versions}"></label>
    <label>Somente estas extensões (vazio = todas)<input name="include_extensions" value="${esc((j.include_extensions || []).join(', '))}" placeholder=".docx, .pdf"></label>
    <label>Ignorar (padrões)<input name="exclude_patterns" value="${esc((j.exclude_patterns || []).join(', '))}" placeholder="*.tmp, node_modules, .git"></label>
    <label>Intervalo (horas)<input name="interval_hours" type="number" min="0.1" step="0.1" value="${j.interval_hours || 24}"></label>
    <label class="check"><input type="checkbox" name="skip_unchanged" ${j.skip_unchanged !== false ? 'checked' : ''}> Não criar versão se nada mudou</label>
    <label class="check"><input type="checkbox" name="enabled" ${j.enabled !== false ? 'checked' : ''}> Executar automaticamente</label></div>
    <hr><div class="row"><button class="primary" type="submit">Salvar</button><button type="button" data-act="bk-cancel">Cancelar</button></div></form>`;
}

/* ----- Histórico ----- */
function viewHistorico() {
  const f = UI.historyFilters;
  const ops = ['', 'move', 'organize', 'backup', 'restore', 'quarantine', 'undo', 'review', 'rule_save', 'rule_delete', 'rule_priority', 'rule_toggle', 'config_save', 'external_change', 'backup_retention'];
  const rows = UI.history || [];
  return `${header('Histórico', 'Tudo fica gravado no computador (history/events.jsonl): o que foi movido, de onde, para onde, por qual regra e quando.')}
  <form class="card" id="historyForm"><div class="form" style="grid-template-columns:2fr 1fr 1fr 1fr auto;align-items:end">
    <label>Buscar (nome, pasta, regra…)<input name="q" value="${esc(f.q || '')}"></label>
    <label>Operação<select name="operation">${ops.map(o => `<option value="${o}" ${o === (f.operation || '') ? 'selected' : ''}>${o ? esc(OPS[o] || o) : 'Todas'}</option>`).join('')}</select></label>
    <label>Status<select name="status">${['', 'ok', 'error', 'partial', 'pending', 'unchanged', 'detected'].map(s => `<option value="${s}" ${s === (f.status || '') ? 'selected' : ''}>${s ? STATUS_TEXT[s] : 'Todos'}</option>`).join('')}</select></label>
    <label>Data<input name="date" type="date" value="${esc(f.date || '')}"></label>
    <button class="primary">Filtrar</button></div></form>
  <div class="card"><div class="spread"><h2>${rows.length} registro(s)</h2><button data-act="report-today">Relatório PDF de hoje</button></div>
  ${rows.length ? `<div class="table-wrap"><table><thead><tr><th>Data</th><th>Operação</th><th>Status</th><th>Arquivo / detalhe</th><th>Regra</th><th></th></tr></thead><tbody>${rows.map(e => eventRow(e, true)).join('')}</tbody></table></div>` : empty('Nenhum registro para este filtro.')}</div>`;
}

/* ----- Ferramentas (funções extras do projeto 0.9) ----- */
function toolResult(name) {
  const r = UI.tools[name];
  if (r === undefined) return '';
  if (name === 'suggestions') return r.length ? `<div class="table-wrap"><table><thead><tr><th>Arquivo</th><th>Categoria</th><th>Formato</th><th></th></tr></thead><tbody>${r.map((s, i) => `<tr><td class="path small">${esc(s.file)}</td><td>${esc(s.category)}</td><td class="small">${esc(s.format)}</td><td><button class="icon" data-act="sugg-rule" data-i="${i}">Criar regra</button></td></tr>`).join('')}</tbody></table></div>` : empty('Todos os arquivos já têm regra.');
  if (name === 'duplicates') return r.length ? r.map(g => `<div class="card" style="padding:10px;margin-top:8px"><b>${g.files.length} cópias · ${bytes(g.bytes_each)} cada</b><div class="small mono">${esc(g.sha256.slice(0, 16))}…</div>${g.files.map((f, i) => `<div class="spread small"><span class="path">${esc(f)}</span>${i ? `<button class="icon danger" data-act="dup-del" data-path="${esc(f)}" data-keep="${esc(g.files[0])}">Apagar esta cópia</button>` : badge('mantida', 'ok')}</div>`).join('')}</div>`).join('') : empty('Nenhum duplicado encontrado.');
  if (name === 'archive') return `<p class="small">${r.count} item(ns) · ${bytes(r.total_bytes)} · ferramenta: ${esc(r.tool)} ${r.risky.length ? badge(`${r.risky.length} executável(is)`, 'err') : ''}</p><div class="table-wrap" style="max-height:240px"><table><tbody>${r.entries.slice(0, 300).map(e => `<tr><td class="path small">${esc(e.name)}</td><td class="small">${bytes(e.bytes)}</td></tr>`).join('')}</tbody></table></div>`;
  if (name === 'sandbox') return `<p class="small">Sandbox <code>${esc(r.id)}</code> em <code>${esc(r.path)}</code> — ${r.files} cópia(s).</p><div class="table-wrap" style="max-height:240px"><table><tbody>${r.results.map(x => `<tr><td class="small">${esc(x.file)}</td><td class="small">${esc(x.rule || '—')}</td><td class="small">${esc(x.note)}</td></tr>`).join('')}</tbody></table></div>`;
  if (name === 'storage') return `<div class="table-wrap"><table><thead><tr><th>Data</th><th>Pasta</th><th>Arquivos</th><th>Tamanho</th></tr></thead><tbody>${r.slice(-15).reverse().map(x => `<tr><td class="small">${when(x.timestamp)}</td><td class="path small">${esc(x.directory)}</td><td>${x.files}</td><td>${bytes(x.bytes)}</td></tr>`).join('')}</tbody></table></div>`;
  if (name === 'filehistory') return r.length ? `<div class="table-wrap"><table><tbody>${r.map(x => `<tr><td>${esc(x.job)}</td><td class="mono">${esc(x.version_id)}</td><td class="small">${esc(x.sha256.slice(0, 12))}…</td><td>${bytes(x.bytes)}</td><td><button class="icon" data-act="bk-restore-one" data-job="${x.job_id}" data-v="${x.version_id}" data-entry="${esc(x.entry)}">Restaurar esta versão</button></td></tr>`).join('')}</tbody></table></div>` : empty('Arquivo não encontrado em nenhum backup.');
  return `<pre class="mono small" style="white-space:pre-wrap">${esc(JSON.stringify(r, null, 2))}</pre>`;
}
function listEditor(name, columns, items) {
  return `<div class="list-editor" data-list="${name}">${(items || []).map(it => `<div class="form le-row" style="grid-template-columns:${columns.map(() => '1fr').join(' ')} auto;align-items:end">${columns.map(c => `<label>${c.label}<input name="${c.key}" type="${c.type || 'text'}" value="${esc(c.key === 'max_mb' ? (it.max_bytes ? it.max_bytes / 1048576 : '') : (Array.isArray(it[c.key]) ? it[c.key].join(', ') : it[c.key] ?? ''))}" ${c.ph ? `placeholder="${esc(c.ph)}"` : ''}></label>`).join('')}<button type="button" class="icon danger" data-act="le-remove">✕</button></div>`).join('')}
    <div class="row" style="margin-top:8px"><button type="button" data-act="le-add" data-cols='${esc(JSON.stringify(columns))}'>+ Adicionar</button><button type="button" class="primary" data-act="le-save" data-list="${name}">Salvar</button></div></div>`;
}
function viewFerramentas() {
  const cats = Object.entries(S.config.categories || {}).map(([name, exts]) => ({ name, exts }));
  return `${header('Ferramentas', 'Recursos extras: classificação sugerida, duplicados, compactados, sandbox, integridade, relatórios, limites, vencimentos e mais.')}
  <div class="grid g2">
    <div class="card"><h2>Classificação sugerida</h2><p class="small muted">Sugere categoria e destino para arquivos sem regra (heurística por extensão e formato real).</p><button data-act="tool" data-tool="suggestions">Analisar pastas monitoradas</button>${toolResult('suggestions')}</div>
    <div class="card"><h2>Arquivos duplicados</h2><p class="small muted">Agrupa por tamanho e confirma por SHA-256. A primeira cópia é mantida.</p><button data-act="tool" data-tool="duplicates">Procurar duplicados</button>${toolResult('duplicates')}</div>
    <div class="card"><h2>Arquivos compactados</h2><p class="small muted">ZIP/TAR: inspecionar e extrair com segurança. RAR/7Z: inspecionar usando o 7-Zip instalado.</p>
      <div class="form"><label class="full">Arquivo<input id="arcPath" placeholder="caminho completo do .zip/.rar/.7z/.tar"></label><label class="two">Extrair para<input id="arcDest"></label></div>
      <div class="row" style="margin-top:8px"><button data-act="arc-inspect">Inspecionar</button><button data-act="arc-extract">Extrair</button></div>${toolResult('archive')}</div>
    <div class="card"><h2>Sandbox de regras</h2><p class="small muted">Copia os arquivos para uma área isolada e aplica as regras nas cópias. Os originais não são tocados.</p>
      <div class="row"><button data-act="sandbox-run">Executar sandbox</button><button data-act="sandbox-list">Listar sandboxes</button></div>${toolResult('sandbox')}${UI.tools.sandboxes ? UI.tools.sandboxes.map(s => `<div class="spread small"><code>${esc(s.id)}</code> ${s.files} arquivo(s)<button class="icon danger" data-act="sandbox-del" data-id="${s.id}">Apagar</button></div>`).join('') || empty('Nenhuma sandbox.') : ''}</div>
    <div class="card"><h2>Integridade (SHA-256)</h2><div class="form"><label class="full">Arquivo<input id="intPath"></label><label class="full">Hash esperado (opcional)<input id="intHash"></label></div><button style="margin-top:8px" data-act="integrity">Calcular</button>${toolResult('integrity')}</div>
    <div class="card"><h2>Renomear com modelo</h2><div class="form"><label class="full">Arquivo<input id="renPath"></label><label class="full">Modelo<input id="renPattern" placeholder="{date}_{name}.{ext}"></label></div><button style="margin-top:8px" data-act="rename">Renomear</button>${toolResult('rename')}</div>
    <div class="card"><h2>Relatórios</h2><div class="form"><label>Dia<input id="repDay" type="date" value="${new Date().toISOString().slice(0, 10)}"></label></div><div class="row" style="margin-top:8px"><button data-act="report">Gerar e baixar PDF</button></div></div>
    <div class="card"><h2>Versões de um arquivo nos backups</h2><div class="form"><label class="full">Caminho original do arquivo<input id="fhPath"></label></div><button style="margin-top:8px" data-act="file-history">Procurar</button>${toolResult('filehistory')}</div>
    <div class="card"><h2>Armazenamento</h2><p class="small muted">Mede o espaço ocupado pelas pastas monitoradas (também feito automaticamente a cada hora).</p><div class="row"><button data-act="storage-now">Medir agora</button><button data-act="storage-hist">Ver medições</button></div>${toolResult('storage')}
      <h3>Limites de espaço (aviso ao chegar em 90%)</h3>${listEditor('limits', [{ key: 'path', label: 'Pasta (vazio = monitoradas)' }, { key: 'category', label: 'Categoria (opcional)' }, { key: 'max_mb', label: 'Máximo (MB)', type: 'number' }], S.config.limits)}</div>
    <div class="card"><h2>Vencimentos de documentos</h2><p class="small muted">Avisa no painel 30 dias antes.</p>${listEditor('due_dates', [{ key: 'description', label: 'Descrição' }, { key: 'file', label: 'Arquivo (opcional)' }, { key: 'due', label: 'Vence em', type: 'date' }], S.config.due_dates)}</div>
    <div class="card"><h2>Projetos</h2><p class="small muted">Uma regra ligada a um projeto envia os arquivos para a pasta do projeto.</p>${listEditor('projects', [{ key: 'name', label: 'Nome' }, { key: 'directory', label: 'Pasta (caminho completo)' }], S.config.projects)}</div>
    <div class="card"><h2>Categorias personalizadas</h2><p class="small muted">Prontas: ${Object.keys(S.categories_builtin).map(esc).join(', ')}.</p>${listEditor('categories', [{ key: 'name', label: 'Categoria' }, { key: 'exts', label: 'Extensões', ph: '.psd, .ai' }], cats)}</div>
    <div class="card"><h2>Observações</h2><form id="noteForm" class="form"><label>Tipo<select name="type"><option value="file">Arquivo</option><option value="rule">Regra</option><option value="operation">Operação</option><option value="backup">Backup</option></select></label><label class="two">Referência (caminho, nome da regra…)<input name="ref"></label><label class="full">Texto<textarea name="text" required></textarea></label><div><button class="primary">Salvar observação</button></div></form>
      ${S.notes.slice().reverse().map(n => `<div class="spread small" style="border-top:1px solid var(--border);padding-top:6px;margin-top:6px"><div>${badge(n.type)} <b>${esc(n.ref)}</b><br>${esc(n.text)}<br><span class="muted">${when(n.updated)}</span></div><button class="icon danger" data-act="note-del" data-id="${n.id}">✕</button></div>`).join('')}</div>
  </div>`;
}

/* ----- Segurança ----- */
function viewSeguranca() {
  const c = S.config;
  return `${header('Segurança', 'Quarentena, proteções, exclusões, perfis com PIN, senha para operações críticas e pareamento.')}
  <div class="grid g2">
    <div class="card"><h2>Quarentena (${S.quarantine.length})</h2><p class="small muted">Arquivos suspeitos ficam isolados na pasta de dados e nunca são executados.</p>
      <label class="check"><input type="checkbox" id="qAuto" ${c.quarantine_risky ? 'checked' : ''}> Enviar automaticamente executáveis e arquivos com extensão disfarçada para a quarentena</label>
      ${S.quarantine.length ? `<div class="table-wrap" style="margin-top:8px"><table><tbody>${S.quarantine.map(q => `<tr><td class="path">${esc(q.name)}<br><span class="small muted">${esc(q.format)} · ${bytes(q.bytes)}</span></td><td><div class="row"><button class="icon" data-act="q-release" data-name="${esc(q.name)}">Liberar…</button><button class="icon danger" data-act="q-delete" data-name="${esc(q.name)}">Apagar</button></div></td></tr>`).join('')}</tbody></table></div>` : empty('Quarentena vazia.')}</div>
    <form class="card" id="protForm"><h2>Proteções e exclusões</h2>
      <label>Caminhos protegidos (nunca movidos automaticamente; um por linha)<textarea name="protected">${esc(c.protected_paths.join('\n'))}</textarea></label>
      <label>Pastas excluídas da varredura (uma por linha)<textarea name="ex_paths">${esc(c.exclusions.paths.join('\n'))}</textarea></label>
      <div class="form"><label>Nomes exatos ignorados<input name="ex_names" value="${esc(c.exclusions.names.join(', '))}"></label><label class="two">Extensões ignoradas<input name="ex_exts" value="${esc(c.exclusions.extensions.join(', '))}" placeholder=".iso, .torrent"></label></div>
      <button class="primary" style="margin-top:8px">Salvar proteções</button></form>
    <div class="card"><h2>Perfis</h2><p class="small muted">Perfil ativo: <b>${esc(S.active_profile)}</b>. Perfis limitam o que pode ser feito pelo painel (não substituem as contas do sistema).</p>
      ${c.profiles.map(p => `<div class="spread" style="border-top:1px solid var(--border);padding:8px 0"><div><b>${esc(p.name)}</b> ${p.has_pin ? badge('PIN', 'info') : ''}<br><span class="small muted">${p.permissions.includes('*') ? 'todas as permissões' : p.permissions.map(x => esc(S.permissions[x] || x)).join('; ')}</span></div>
      <div class="row">${p.name !== S.active_profile ? `<button class="icon" data-act="profile-switch" data-name="${esc(p.name)}" data-pin="${p.has_pin ? 1 : 0}">Usar</button><button class="icon danger" data-act="profile-del" data-name="${esc(p.name)}">Excluir</button>` : badge('ativo', 'ok')}</div></div>`).join('')}
      <form id="profileForm"><h3>Criar/editar perfil</h3><div class="form"><label>Nome<input name="name" required></label><label>PIN (4–8 dígitos, opcional)<input name="pin" inputmode="numeric" type="password"></label></div>
      <div class="row" style="margin:8px 0">${Object.entries(S.permissions).map(([k, v]) => `<label class="check small"><input type="checkbox" name="perm" value="${k}" ${k === 'read' ? 'checked' : ''}> ${esc(v)}</label>`).join('')}</div><button class="primary">Salvar perfil</button></form></div>
    <div class="card"><h2>Senha de operações críticas</h2><p class="small muted">Se definida, é pedida para restaurar backups, importar/restaurar configurações, apagar duplicados e mexer na quarentena. Status: ${c.critical_password_enabled ? badge('ativada', 'ok') : badge('desativada')}</p>
      <form id="passForm" class="form">${c.critical_password_enabled ? '<label>Senha atual<input name="current" type="password" required></label>' : ''}<label>Nova senha (vazio = remover)<input name="new" type="password" minlength="6"></label><div style="align-self:end"><button class="primary">Salvar senha</button></div></form>
      <h2 style="margin-top:20px">Conexão com o site</h2><p class="small">Origens autorizadas a falar com o programa:<br>${S.allowed_origins.map(o => `<code>${esc(o)}</code>`).join('<br>')}</p>
      <p class="small muted">O site recebe um token aleatório ao ser aberto pelo atalho. Para outro navegador, use o código mostrado por <code>organizalocal codigo</code>.</p>
      <button class="danger" data-act="revoke">Revogar todos os acessos</button></div>
  </div>`;
}

/* ----- Sistema (conceitos de SO) ----- */
function viewSistema() {
  const d = UI.sysinfo;
  if (!d) { setTimeout(() => act('sys-refresh'), 0); return `${header('Sistema', 'Carregando informações do sistema operacional…')}`; }
  const gib = b => bytes(b);
  return `${header('Sistema operacional', 'Informações coletadas pelo programa local — mostram na prática os conceitos de processos, memória, armazenamento, variáveis de ambiente e permissões.', '<button data-act="sys-refresh">Atualizar</button>')}
  <div class="grid g3">
    <div class="card"><h2>Sistema</h2><p>${esc(d.system.os)} ${esc(d.system.release)} · ${esc(d.system.machine)}<br>Máquina: <b>${esc(d.system.hostname)}</b><br>Python ${esc(d.system.python)}<br><span class="small muted path">${esc(d.system.executable)}</span></p></div>
    <div class="card"><h2>Processo do serviço</h2><p>PID <b>${d.process.pid}</b> · PPID ${d.process.ppid}<br>Usuário: ${esc(d.process.user)}<br>Memória (RSS): <b>${gib(d.process.rss_bytes)}</b><br>Em execução há ${Math.floor(d.process.uptime_seconds / 60)} min<br>Threads: ${d.process.threads.map(esc).join(', ')}</p></div>
    <div class="card"><h2>CPU e memória</h2><p>${esc(d.cpu.model)}<br>${d.cpu.cores} núcleos${d.cpu.load_average ? ` · carga ${d.cpu.load_average.join(' / ')}` : ''}</p>
      <p>Memória: ${gib(d.memory.total - d.memory.available)} usados de ${gib(d.memory.total)} (${d.memory.percent_used}%)</p><div class="meter"><i style="width:${d.memory.percent_used || 0}%"></i></div><p class="small muted">Fonte: ${esc(d.memory.source)}</p></div>
  </div>
  <div class="card"><h2>Armazenamento</h2>${d.disks.map(k => `<div style="margin-bottom:10px"><div class="spread small"><span><b>${esc(k.label)}</b> <code>${esc(k.path)}</code>${k.same_disk_as_previous ? ' (mesmo disco)' : ''}</span><span>${gib(k.free)} livres de ${gib(k.total)}</span></div><div class="meter"><i style="width:${k.percent_used}%"></i></div></div>`).join('')}</div>
  <div class="grid g2">
    <div class="card"><h2>Variáveis de ambiente usadas</h2><div class="table-wrap"><table><tbody>${Object.entries(d.environment).map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td class="path small">${esc(v)}</td></tr>`).join('')}</tbody></table></div></div>
    <div class="card"><h2>Pasta de dados e agendador</h2><p><code>${esc(d.data_dir.path)}</code><br>Permissões: <b class="mono">${esc(d.data_dir.permissions)}</b> ${d.data_dir.owner_only === true ? badge('só o dono acessa', 'ok') : `<span class="small muted">${esc(String(d.data_dir.owner_only))}</span>`}</p>
      <p>Agendador: ${d.scheduler.running ? badge('rodando', 'ok') : badge('parado', 'err')} verifica a cada ${d.scheduler.check_every_seconds} s<br>Próxima organização: ${when(d.scheduler.next_organize)}${d.scheduler.last_error ? `<br><span class="small" style="color:var(--err)">${esc(d.scheduler.last_error)}</span>` : ''}</p></div>
  </div>`;
}

/* ----- Configurações ----- */
function viewConfig() {
  const c = S.config, sch = c.organize_schedule;
  const days = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];
  return `${header('Configurações', `Salvas em <code>${esc(S.app.data_dir)}</code>. Cada alteração gera uma versão da configuração.`)}
  <form class="card" id="configForm"><h2>Organização automática</h2><div class="form">
    <label class="full">Pastas monitoradas (uma por linha) — padrão: Downloads<textarea name="watch_dirs">${esc(c.watch_dirs.join('\n'))}</textarea></label>
    <label>Frequência<select name="frequency">${[['interval', 'A cada X minutos'], ['daily', 'Diária'], ['weekly', 'Semanal'], ['off', 'Desligada']].map(([v, t]) => `<option value="${v}" ${sch.frequency === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
    <label>Intervalo (minutos) — padrão 60<input name="interval_minutes" type="number" min="1" value="${sch.interval_minutes}"></label>
    <label>Horário (diária/semanal)<input name="time" type="time" value="${esc(sch.time)}"></label>
    <label>Dia da semana<select name="weekday">${days.map((d, i) => `<option value="${i}" ${Number(sch.weekday) === i ? 'selected' : ''}>${d}</option>`).join('')}</select></label>
    <label>Arquivo já existe no destino<select name="conflict_policy"><option value="rename" ${c.conflict_policy === 'rename' ? 'selected' : ''}>Salvar com nome numerado</option><option value="review" ${c.conflict_policy === 'review' ? 'selected' : ''}>Enviar para revisão</option><option value="skip" ${c.conflict_policy === 'skip' ? 'selected' : ''}>Não mover</option></select></label>
    <label>Ignorar arquivos modificados há menos de (segundos)<input name="min_file_age_seconds" type="number" min="0" value="${c.min_file_age_seconds}"></label>
    <label class="two">Destino padrão para arquivos sem regra (vazio = ficam onde estão)<input name="default_destination" value="${esc(c.default_destination)}"></label>
    <label>Modelo de nome global (opcional)<input name="rename_pattern" value="${esc(c.rename_pattern)}" placeholder="{date}_{name}.{ext}"></label>
    <label class="check"><input type="checkbox" name="recursive" ${c.recursive ? 'checked' : ''}> Incluir subpastas</label>
    <label class="check"><input type="checkbox" name="organize_on_start" ${c.organize_on_start ? 'checked' : ''}> Organizar quando o serviço iniciar</label>
    <label>Versões de backup padrão<input name="default_max_versions" type="number" min="1" max="100" value="${c.default_max_versions}"></label></div>
    <h2 style="margin-top:20px">Site e aparência</h2><div class="form">
    <label class="two">URL do site publicado na Vercel (o atalho abre este endereço)<input name="site_url" value="${esc(c.site_url)}" placeholder="https://organiza-local.vercel.app"></label>
    <label>Tema<select name="theme">${['claro', 'escuro', 'neon'].map(t => `<option ${c.theme === t ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
    <label class="full">Outras origens autorizadas (uma por linha, ex.: previews da Vercel)<textarea name="extra_origins">${esc((c.extra_origins || []).join('\n'))}</textarea></label></div>
    <hr><button class="primary">Salvar configurações</button></form>
  <div class="grid g2">
    <div class="card"><h2>Exportar / importar</h2><p class="small muted">Leve suas regras para outro computador.</p><div class="row"><button data-act="cfg-export">Exportar JSON</button><label class="btn">Importar JSON<input type="file" id="cfgImport" accept=".json,application/json" hidden></label></div></div>
    <div class="card"><h2>Versões da configuração</h2><button data-act="cfg-versions">Listar versões</button>${UI.tools.versions ? `<div class="table-wrap" style="max-height:260px;margin-top:8px"><table><tbody>${UI.tools.versions.map(v => `<tr><td class="small">${when(v.timestamp)}</td><td class="mono small">${esc(v.filename)}</td><td><button class="icon" data-act="cfg-restore" data-file="${esc(v.filename)}">Restaurar</button></td></tr>`).join('')}</tbody></table></div>` : ''}</div>
  </div>`;
}

const VIEWS = { painel: viewPainel, regras: viewRegras, organizacao: viewOrganizacao, backups: viewBackups, historico: viewHistorico, ferramentas: viewFerramentas, seguranca: viewSeguranca, sistema: viewSistema, config: viewConfig };

function render() {
  if (!S) return;
  $$('#nav button[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === TAB));
  $('#main').innerHTML = VIEWS[TAB]();
  if (TAB === 'historico' && UI.history === null) act('history-load');
}

/* ----- Telas de conexão ----- */
function renderOffline() {
  setConnection(false);
  $('#main').innerHTML = `<section class="card"><h1>O programa local não está aberto</h1>
    <p>Este site só mostra e controla o OrganizaLocal que roda no <b>seu computador</b>. Nenhum arquivo é enviado para a internet.</p>
    <ol><li><b>Windows:</b> clique no atalho <b>OrganizaLocal</b> da Área de Trabalho ou do Menu Iniciar.</li>
    <li><b>Linux:</b> rode <code>organizalocal open</code> no terminal (ou use o atalho do menu de aplicativos).</li>
    <li>Se o navegador perguntar sobre <b>acesso à rede local</b>, clique em <b>Permitir</b> — é assim que o site fala com o programa em 127.0.0.1.</li></ol>
    <p class="small muted">Procurando o programa em <code>${esc(API)}</code></p><button class="primary" data-act="retry">Tentar novamente</button></section>`;
}
function renderPairing() {
  setConnection(false, '● Aguardando pareamento');
  $('#main').innerHTML = `<form class="card" id="pairForm" style="max-width:520px"><h1>Conectar ao programa</h1>
    <p>Abra o site pelo <b>atalho do OrganizaLocal</b> para entrar automaticamente, ou digite o código de 6 dígitos exibido por <code>organizalocal codigo</code> (ou no terminal do serviço).</p>
    <label>Código de pareamento<input name="code" inputmode="numeric" maxlength="6" required autofocus></label>
    <div class="row" style="margin-top:12px"><button class="primary">Conectar</button></div></form>`;
}

/* ---------------------------------------------------------------------------
   4. AÇÕES
   --------------------------------------------------------------------------- */
async function act(name, el = {}) {
  const d = el.dataset || {};
  switch (name) {
    case 'retry': return start();
    /* Organização */
    case 'simulate-go': TAB = 'organizacao'; safeSet('ol_tab', TAB); render(); return act('simulate');
    case 'simulate': {
      const r = await run('simulate', {}, { reload: false });
      if (r) { UI.simulation = r; UI.simFilter = 'todos'; render(); }
      return;
    }
    case 'rule-test': {
      const rule = S.rules.find(r => r.id === d.id);
      const r = await run('simulate', { only_rule: d.id }, { reload: false });
      if (r) { r.only_rule_name = rule?.name; UI.simulation = r; UI.simFilter = 'move'; TAB = 'organizacao'; render(); }
      return;
    }
    case 'organize': {
      const ok = await confirmBox({ title: 'Organizar agora?', text: 'As regras <b>ativas</b> serão aplicadas e os arquivos serão <b>movidos de verdade</b>. Dica: simule antes.', okText: 'Organizar' });
      if (!ok) return;
      const r = await run('organize', {}, { success: x => x.errors.length ? `Concluído com ${x.errors.length} falha(s).` : `${x.moved} arquivo(s) organizado(s).` });
      if (r) { UI.lastRun = r; UI.simulation = null; TAB = 'organizacao'; render(); }
      return;
    }
    case 'sim-export': { const r = await run('simulate_export', {}, { reload: false }); if (r) download('exports', r.filename); return; }
    case 'rev': {
      const payload = { id: d.id, decision: d.d };
      if (d.d === 'move') {
        const v = await confirmBox({ title: 'Mover para qual pasta?', fields: '<label>Pasta ou caminho completo<input name="destination" required></label>', okText: 'Mover' });
        if (!v) return; payload.destination = v.destination;
      }
      if (d.d === 'replace') {
        const ok = await confirmBox({ title: 'Substituir arquivo existente?', text: 'O arquivo que já está no destino será guardado em "protected_versions" antes de ser substituído.', danger: true, okText: 'Substituir' });
        if (!ok) return; payload.confirm = true;
      }
      return run('review_decide', payload, { success: 'Decisão aplicada.' });
    }
    /* Regras */
    case 'rule-new': UI.ruleForm = { priority: 5, enabled: true, create_destination: true, exceptions: [], conditions: {} }; render(); window.scrollTo(0, 0); return;
    case 'rule-edit': UI.ruleForm = structuredClone(S.rules.find(r => r.id === d.id)); render(); window.scrollTo(0, 0); return;
    case 'rule-cancel': UI.ruleForm = null; return render();
    case 'exc-add': $('#excList').insertAdjacentHTML('beforeend', excRowHtml({})); return;
    case 'exc-remove': el.closest('.exc-row').remove(); return;
    case 'prio': return run('rule_priority', { id: d.id, delta: Number(d.delta) });
    case 'toggle': return run('rule_toggle', { id: d.id, enabled: d.enabled === '1' }, { success: d.enabled === '1' ? 'Regra ativada.' : 'Regra desativada.' });
    case 'rule-dup': return run('rule_duplicate', { id: d.id }, { success: 'Cópia criada (desativada).' });
    case 'rule-del': {
      const rule = S.rules.find(r => r.id === d.id);
      const ok = await confirmBox({ title: 'Excluir regra?', text: `A regra <b>${esc(rule.name)}</b> será removida e não será mais aplicada.`, danger: true, okText: 'Excluir' });
      if (ok) return run('rule_delete', { id: d.id, confirm: true }, { success: 'Regra excluída.' });
      return;
    }
    case 'validate': {
      const r = await run('rules_validate', {}, { reload: false });
      if (r) toast(r.length ? `${r.length} problema(s) encontrado(s).` : 'Nenhum problema nas regras.');
      return refresh();
    }
    /* Backups */
    case 'bk-new': UI.backupForm = { mode: 'zip', enabled: true, skip_unchanged: true }; render(); window.scrollTo(0, 0); return;
    case 'bk-edit': UI.backupForm = structuredClone(S.backup_jobs.find(j => j.id === d.id)); render(); window.scrollTo(0, 0); return;
    case 'bk-cancel': UI.backupForm = null; return render();
    case 'bk-run': return run('backup_run', { id: d.id }, { success: r => r.created ? `Versão ${r.version.id} criada (${r.version.files} arquivos).` + (r.removed_versions.length ? ` Retenção removeu ${r.removed_versions.length}.` : '') : r.reason });
    case 'bk-open': return run('open_backups', { job_id: d.id || '' }, { reload: false, success: r => `Aberto: ${r.opened}` });
    case 'bk-del': {
      const v = await confirmBox({ title: 'Excluir regra de backup?', fields: '<label class="check"><input type="checkbox" name="files"> Apagar também os arquivos das versões</label>', danger: true, okText: 'Excluir' });
      if (v) return run('backup_job_delete', { id: d.id, confirm: true, delete_files: !!v.files }, { success: 'Regra de backup excluída.' });
      return;
    }
    case 'bk-lock': return run('backup_lock', { job_id: d.job, version_id: d.v, locked: d.locked === '1' });
    case 'bk-vdel': {
      const v = await confirmBox({ title: 'Apagar esta versão?', text: 'Os arquivos desta versão serão apagados do disco.', danger: true, password: true, okText: 'Apagar' });
      if (v) return run('backup_delete_version', { job_id: d.job, version_id: d.v, confirm: true, password: v.password }, { success: 'Versão apagada.' });
      return;
    }
    case 'bk-verify': { const r = await run('backup_verify', { job_id: d.job, version_id: d.v }, { reload: false }); if (r) toast(r.ok ? `Íntegro: ${r.checked} arquivo(s) conferidos por SHA-256.` : `${r.corrupted.length} arquivo(s) corrompido(s)!`, !r.ok); return; }
    case 'bk-compare': {
      const r = await run('backup_compare', { job_id: d.job, a: $(`#cmpA-${d.job}`).value, b: $(`#cmpB-${d.job}`).value }, { reload: false });
      if (r) showModal(`Comparação ${r.a} → ${r.b}`, `<p>${r.unchanged} sem mudança.</p>${['added', 'removed', 'changed'].map(k => `<h3>${{ added: 'Adicionados', removed: 'Removidos', changed: 'Alterados' }[k]} (${r[k].length})</h3>${r[k].map(f => `<div class="small mono">${esc(f)}</div>`).join('') || '<div class="muted small">nenhum</div>'}`).join('')}`);
      return;
    }
    case 'bk-files': {
      const m = await run('backup_manifest', { job_id: d.job, version_id: d.v }, { reload: false });
      if (m) showModal(`Arquivos da versão ${d.v}`, `<div class="table-wrap" style="max-height:60vh"><table><thead><tr><th>Arquivo original</th><th>Tamanho</th><th>Modificado</th><th></th></tr></thead><tbody>${m.files.map(f => `<tr><td class="path small">${esc(f.path)}</td><td>${bytes(f.bytes)}</td><td class="small">${when(f.mtime)}</td><td><button class="icon" data-act="bk-restore-one" data-job="${d.job}" data-v="${d.v}" data-entry="${esc(f.root + '/' + f.rel)}">Restaurar</button></td></tr>`).join('')}</tbody></table></div>`);
      $$('#modal [data-act]').forEach(b => b.addEventListener('click', () => act(b.dataset.act, b)));
      return;
    }
    case 'bk-restore':
    case 'bk-restore-one': {
      const v = await confirmBox({
        title: name === 'bk-restore' ? `Restaurar versão ${d.v}?` : 'Restaurar este arquivo?', password: true, okText: 'Restaurar',
        text: 'Sem pasta: os arquivos voltam ao local original (o arquivo atual, se diferente, é guardado antes em protected_versions). Com pasta: a versão é recriada lá, sem sobrescrever nada.',
        fields: '<label>Restaurar em outra pasta (opcional)<input name="target"></label>',
      });
      if (!v) return;
      $('#modal').classList.add('hidden');
      return run('backup_restore', { job_id: d.job, version_id: d.v, target_dir: v.target || '', only: d.entry ? [d.entry] : null, confirm: true, password: v.password },
        { success: r => `${r.restored.length} arquivo(s) restaurado(s)` + (r.errors.length ? `, ${r.errors.length} falha(s)` : '') + '.' });
    }
    /* Histórico */
    case 'history-load': UI.history = await run('history', { filters: UI.historyFilters, limit: 500 }, { reload: false }) || []; if (TAB === 'historico') render(); return;
    case 'undo': {
      const ok = await confirmBox({ title: 'Desfazer movimentação?', text: 'O arquivo voltará para a pasta de origem (se não tiver sido alterado depois).', okText: 'Desfazer' });
      if (ok && await run('undo', { event_id: d.id }, { success: 'Movimentação desfeita.' })) { UI.history = null; render(); }
      return;
    }
    case 'note-for': {
      const v = await confirmBox({ title: 'Nova observação', fields: '<label>Texto<textarea name="text" required></textarea></label>', okText: 'Salvar' });
      if (v) return run('note_save', { type: d.type, ref: d.ref, text: v.text }, { success: 'Observação salva.' });
      return;
    }
    case 'report-today': case 'report': {
      const r = await run('report', { day: $('#repDay')?.value || '' }, { reload: false });
      if (r) download('reports', r.filename);
      return;
    }
    /* Ferramentas */
    case 'tool': { const r = await run(d.tool, {}, { reload: false }); if (r) { UI.tools[d.tool] = r; render(); } return; }
    case 'sugg-rule': {
      const s = UI.tools.suggestions[Number(d.i)];
      UI.ruleForm = { name: `${s.category} (${s.extension})`, priority: 5, enabled: true, create_destination: true, destination: s.suggested_destination, conditions: { extensions: s.extension ? [s.extension] : [], keywords: s.extension ? [] : s.keywords }, exceptions: [] };
      TAB = 'regras'; render(); return;
    }
    case 'dup-del': {
      const v = await confirmBox({ title: 'Apagar cópia duplicada?', text: `<code>${esc(d.path)}</code><br>Só é apagada se o conteúdo for idêntico ao da cópia mantida.`, danger: true, password: true, okText: 'Apagar' });
      if (v && await run('duplicate_remove', { path: d.path, keep: d.keep, confirm: true, password: v.password }, { success: 'Cópia apagada.', reload: false })) act('tool', { dataset: { tool: 'duplicates' } });
      return;
    }
    case 'arc-inspect': { const r = await run('archive_inspect', { path: $('#arcPath').value }, { reload: false }); if (r) { UI.tools.archive = r; render(); } return; }
    case 'arc-extract': return run('archive_extract', { path: $('#arcPath').value, directory: $('#arcDest').value }, { reload: false, success: r => `${r.extracted} arquivo(s) extraído(s).` });
    case 'sandbox-run': { const r = await run('sandbox_run', {}, { reload: false }); if (r) { UI.tools.sandbox = r; render(); } return; }
    case 'sandbox-list': UI.tools.sandboxes = await run('sandbox_list', {}, { reload: false }) || []; return render();
    case 'sandbox-del': await run('sandbox_delete', { id: d.id }, { reload: false }); return act('sandbox-list');
    case 'integrity': { const r = await run('integrity', { path: $('#intPath').value, expected: $('#intHash').value }, { reload: false }); if (r) { UI.tools.integrity = r; render(); } return; }
    case 'rename': { const r = await run('rename_file', { path: $('#renPath').value, pattern: $('#renPattern').value }, { reload: false, success: 'Arquivo renomeado.' }); if (r) { UI.tools.rename = r; render(); } return; }
    case 'file-history': { const r = await run('file_history', { path: $('#fhPath').value }, { reload: false }); if (r) { UI.tools.filehistory = r; render(); } return; }
    case 'storage-now': await run('storage_snapshot', {}, { reload: false, success: 'Medição registrada.' }); return act('storage-hist');
    case 'storage-hist': UI.tools.storage = await run('storage_history', {}, { reload: false }) || []; return render();
    case 'le-add': {
      const cols = JSON.parse(d.cols);
      el.closest('.row').insertAdjacentHTML('beforebegin', `<div class="form le-row" style="grid-template-columns:${cols.map(() => '1fr').join(' ')} auto;align-items:end">${cols.map(c => `<label>${c.label}<input name="${c.key}" type="${c.type || 'text'}" ${c.ph ? `placeholder="${esc(c.ph)}"` : ''}></label>`).join('')}<button type="button" class="icon danger" data-act="le-remove">✕</button></div>`);
      return;
    }
    case 'le-remove': el.closest('.le-row').remove(); return;
    case 'le-save': {
      const box = el.closest('.list-editor');
      const rows = $$('.le-row', box).map(row => Object.fromEntries($$('input', row).map(i => [i.name, i.value.trim()])));
      let items = rows.filter(r => Object.values(r).some(Boolean));
      if (d.list === 'limits') items = items.map(r => ({ path: r.path, category: r.category, max_bytes: Math.round(Number(r.max_mb || 0) * 1048576) }));
      if (d.list === 'categories') items = Object.fromEntries(items.map(r => [r.name, csv(r.exts)]));
      return run('list_save', { name: d.list, items }, { success: 'Salvo.' });
    }
    case 'note-del': return run('note_delete', { id: d.id });
    /* Segurança */
    case 'q-release': {
      const v = await confirmBox({ title: 'Liberar arquivo da quarentena?', text: `<b>${esc(d.name)}</b> pode ser perigoso. Só libere se confiar na origem.`, fields: '<label>Mover para a pasta<input name="destination" required></label>', password: true, danger: true, okText: 'Liberar' });
      if (v) return run('quarantine_action', { action: 'release', name: d.name, destination: v.destination, confirm: true, password: v.password }, { success: 'Arquivo liberado.' });
      return;
    }
    case 'q-delete': {
      const v = await confirmBox({ title: 'Apagar definitivamente?', text: `<b>${esc(d.name)}</b>`, password: true, danger: true, okText: 'Apagar' });
      if (v) return run('quarantine_action', { action: 'delete', name: d.name, confirm: true, password: v.password }, { success: 'Arquivo apagado.' });
      return;
    }
    case 'profile-switch': {
      let pin = '';
      if (d.pin === '1') { const v = await confirmBox({ title: `Usar o perfil ${d.name}`, fields: '<label>PIN<input name="pin" type="password" inputmode="numeric" required></label>', okText: 'Entrar' }); if (!v) return; pin = v.pin; }
      return run('profile_switch', { name: d.name, pin }, { success: `Perfil ${d.name} ativo.` });
    }
    case 'profile-del': if (await confirmBox({ title: `Excluir o perfil ${d.name}?`, danger: true, okText: 'Excluir' })) return run('profile_delete', { name: d.name }); return;
    case 'revoke': if (await confirmBox({ title: 'Revogar todos os acessos?', text: 'Este navegador também será desconectado. Abra o site de novo pelo atalho.', danger: true, okText: 'Revogar' })) { await run('pairing_revoke', {}, { reload: false }); renderPairing(); } return;
    /* Sistema */
    case 'sys-refresh': UI.sysinfo = await run('sysinfo', {}, { reload: false }) || null; if (TAB === 'sistema' && UI.sysinfo) render(); return;
    /* Configurações */
    case 'cfg-export': { const r = await run('config_export', {}, { reload: false }); if (r) saveBlob(new Blob([JSON.stringify(r.data, null, 2)], { type: 'application/json' }), r.filename); return; }
    case 'cfg-versions': UI.tools.versions = await run('config_versions', {}, { reload: false }) || []; return render();
    case 'cfg-restore': {
      const v = await confirmBox({ title: 'Restaurar esta versão da configuração?', text: 'A configuração atual também será guardada como versão.', password: true, okText: 'Restaurar' });
      if (v) return run('config_restore', { filename: d.file, confirm: true, password: v.password }, { success: 'Configuração restaurada.' });
      return;
    }
  }
}

/* ----- Envio de formulários ----- */
async function onSubmit(form) {
  const f = new FormData(form);
  switch (form.id) {
    case 'pairForm': {
      try {
        const r = await fetch(`${API}/api/pair`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: f.get('code') }) });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error);
        TOKEN = data.token; sessionStorage.setItem('ol_token', TOKEN);
        return start();
      } catch (err) { return toast(err.message, true); }
    }
    case 'ruleForm': {
      const id = UI.ruleForm.id;
      const r = await run('rule_save', { id, rule: readRuleForm(form) }, { success: id ? 'Regra atualizada.' : 'Regra criada.', reload: false });
      if (r) { UI.ruleForm = null; await refresh(); }
      return;
    }
    case 'backupForm': {
      const id = UI.backupForm.id;
      const job = { name: f.get('name'), mode: f.get('mode'), sources: lines(f.get('sources')), destination: f.get('destination').trim(),
        max_versions: Number(f.get('max_versions')), include_extensions: csv(f.get('include_extensions')), exclude_patterns: csv(f.get('exclude_patterns')),
        interval_hours: Number(f.get('interval_hours')), skip_unchanged: f.has('skip_unchanged'), enabled: f.has('enabled') };
      let r;
      try { r = await call('backup_job_save', { id, job }); }
      catch (err) {
        if (/Confirme/.test(err.message) && await confirmBox({ title: 'Reduzir número de versões?', text: esc(err.message), danger: true, okText: 'Reduzir' })) r = await run('backup_job_save', { id, job, confirm: true }, { reload: false });
        else return toast(err.message, true);
      }
      if (r) { UI.backupForm = null; toast('Regra de backup salva.'); await refresh(); }
      return;
    }
    case 'historyForm': UI.historyFilters = Object.fromEntries([...f].filter(([, v]) => v)); UI.history = null; return act('history-load');
    case 'noteForm': return run('note_save', Object.fromEntries(f), { success: 'Observação salva.' });
    case 'protForm':
      return run('config_update', { changes: { protected_paths: lines(f.get('protected')), exclusions: { paths: lines(f.get('ex_paths')), names: csv(f.get('ex_names')), extensions: csv(f.get('ex_exts')) } } }, { success: 'Proteções salvas.' });
    case 'profileForm': return run('profile_save', { name: f.get('name'), pin: f.get('pin'), permissions: f.getAll('perm') }, { success: 'Perfil salvo.' });
    case 'passForm': return run('password_set', { new: f.get('new') || '', current: f.get('current') || '' }, { success: 'Senha atualizada.' });
    case 'configForm': {
      const changes = {
        watch_dirs: lines(f.get('watch_dirs')), recursive: f.has('recursive'), organize_on_start: f.has('organize_on_start'),
        organize_schedule: { frequency: f.get('frequency'), interval_minutes: Number(f.get('interval_minutes')), time: f.get('time'), weekday: Number(f.get('weekday')) },
        conflict_policy: f.get('conflict_policy'), min_file_age_seconds: Number(f.get('min_file_age_seconds')),
        default_destination: f.get('default_destination').trim(), rename_pattern: f.get('rename_pattern'),
        default_max_versions: Number(f.get('default_max_versions')), site_url: f.get('site_url').trim(), theme: f.get('theme'), extra_origins: lines(f.get('extra_origins')),
      };
      return run('config_update', { changes }, { success: 'Configurações salvas.' });
    }
  }
}

/* ----- Inicialização ----- */
document.addEventListener('click', e => {
  const tab = e.target.closest('#nav button[data-tab], [data-tab-go]');
  if (tab) {
    TAB = tab.dataset.tab || tab.dataset.tabGo; safeSet('ol_tab', TAB);
    $('#nav').classList.remove('open');
    if (TAB === 'sistema') UI.sysinfo = null;
    render(); window.scrollTo(0, 0); return;
  }
  const el = e.target.closest('[data-act]');
  if (el && !el.closest('#modal')) { e.preventDefault(); act(el.dataset.act, el); }
});
document.addEventListener('submit', e => { if (e.target.closest('#modal')) return; e.preventDefault(); onSubmit(e.target); });
document.addEventListener('change', async e => {
  if (e.target.id === 'simFilter') { UI.simFilter = e.target.value; render(); }
  if (e.target.id === 'qAuto') run('config_update', { changes: { quarantine_risky: e.target.checked } }, { success: 'Preferência salva.' });
  if (e.target.id === 'cfgImport' && e.target.files[0]) {
    try {
      const data = JSON.parse(await e.target.files[0].text());
      const v = await confirmBox({ title: 'Importar configuração?', text: 'Regras e configurações atuais serão substituídas (a atual vira uma versão).', password: true, okText: 'Importar' });
      if (v) run('config_import', { data, confirm: true, password: v.password }, { success: r => `${r.rules} regra(s) importada(s).` });
    } catch { toast('Arquivo JSON inválido.', true); }
  }
});
$('#menuToggle').addEventListener('click', () => $('#nav').classList.toggle('open'));

async function start() {
  const alive = await ping();
  if (!alive) return renderOffline();
  if (!TOKEN) return renderPairing();
  try { await refresh(); } catch (err) { if (TOKEN) toast(err.message, true); }
}
start();
// Atualiza o painel periodicamente (sem atrapalhar formulários abertos).
setInterval(() => {
  if (!TOKEN || !S || document.hidden || UI.ruleForm || UI.backupForm || !$('#modal').classList.contains('hidden')) return;
  if (['painel', 'organizacao', 'backups'].includes(TAB) && !document.activeElement?.matches('input,textarea,select')) refresh().catch(() => renderOffline());
}, 30000);

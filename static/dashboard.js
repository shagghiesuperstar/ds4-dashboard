// Dwarfstar DS4 Dashboard — Live telemetry, config, benchmarks, MCP
// Clean antirez-style: minimal, functional, readable.

const POLL_MS = 2000;
const MAX_POINTS = 60;

const state = {
  config: null, schema: null, lastStatus: null,
  benchmarkSuites: [], models: [], modelDescriptions: {},
  configProfiles: [], profileDetails: {},
  expandedProfileId: null, editingProfileId: null,
  compareProfiles: [], compareRunning: false,
  tokensHistory: [], systemHistory: [],
  benchmarkHistoryChart: null,
};

const $ = (id) => document.getElementById(id);

function fmtBytes(bytes) {
  if (bytes == null || Number.isNaN(Number(bytes))) return '--';
  const v = Number(bytes);
  const units = ['B','KiB','MiB','GiB','TiB'];
  let n = Math.abs(v), u = 0;
  while (n >= 1024 && u < units.length-1) { n /= 1024; u++; }
  return `${(v<0?-n:n).toFixed(u===0?0:1)} ${units[u]}`;
}
function fmtMiB(mib) {
  if (mib == null || Number.isNaN(Number(mib))) return '--';
  return fmtBytes(Number(mib) * 1024 * 1024);
}
function fmtNum(v, d=1) {
  if (v == null || Number.isNaN(Number(v))) return '--';
  return Number(v).toLocaleString(undefined, {maximumFractionDigits:d,minimumFractionDigits:d});
}
function fmtPct(v) {
  if (v == null || Number.isNaN(Number(v))) return '--';
  return fmtNum(v,1) + '%';
}
function fmtVal(v) {
  if (v == null) return '—';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v) || '—';
}
function fmtDur(s) {
  if (s == null || Number.isNaN(Number(s))) return '--';
  const t = Math.max(0, Math.floor(Number(s)));
  const h = Math.floor(t/3600), m = Math.floor((t%3600)/60), sec = t%60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}
function setText(id, v) { const e = $(id); if (e) e.textContent = v; }
function hasVal(v) { return v != null && v !== ''; }
function numVal(v) { return hasVal(v) && !Number.isNaN(Number(v)) ? Number(v) : null; }
function pathBase(p) { return typeof p === 'string' && p ? p.split('/').pop() : ''; }
function avg(stats, m) { const v = stats?.[m]?.avg; return numVal(v); }
function bestStats(status) {
  const primary = status.model_averages || {};
  const all = status.model_averages_all || {};
  let best = null;
  for (const [k,s] of Object.entries(all)) {
    const cnt = s?.count || 0;
    if (cnt > 0 && (!best || s.avg > best.avg)) best = {name:k, ...s};
  }
  return {primary, all, best};
}
function slug(s) {
  return String(s||'').trim().toLowerCase().replace(/\s+/g,'-').replace(/[^a-z0-9_-]+/g,'').replace(/-{2,}/g,'-').replace(/^-|-$/g,'');
}

// ── UI Update ──
function updateStatus(status) {
  state.lastStatus = status;
  const telem = status.telemetry || {};
  const sys = status.system || {};
  const kv = status.kv_cache || {};
  const stateStr = status.state || 'unknown';
  const running = status.running;

  // State badge
  const badge = $('status-badge');
  if (badge) {
    badge.dataset.state = stateStr;
    const dot = badge.querySelector('.status-dot');
    if (dot) dot.style.animation = running ? 'none' : '';
  }
  setText('state-label', stateStr.toUpperCase());

  // Hero metrics
  setText('tokens-sec', fmtNum(telem.tokens_sec));
  setText('prefill-sec', fmtNum(telem.prefill_tokens_sec));
  setText('context-window', fmtVal(telem.context_window));
  setText('kv-cache', fmtBytes(kv.budget_bytes || telem.kv_cache_budget_bytes));
  setText('shader-count', fmtVal(telem.shader_count));
  setText('status-message', telem.status_message || status.error || 'OK');
  setText('endpoint', `${status.port || '?'}`);

  // Monitoring
  const mem = sys.memory || {};
  setText('memory-pressure', fmtBytes(mem.pressure_level === 'critical' ? mem.active_bytes : mem.free_bytes));
  setText('memory-used', fmtBytes(mem.active_bytes));
  setText('memory-total', 'Total ' + fmtBytes(mem.total_bytes));
  setText('memory-free', 'Free ' + fmtBytes(mem.free_bytes));
  setText('swap-used', 'Swap ' + fmtBytes(mem.swap_bytes));
  const memPct = numVal(mem.active_bytes) && numVal(mem.total_bytes) ? Number(mem.active_bytes)/Number(mem.total_bytes)*100 : 0;
  const mf = $('memory-fill');
  if (mf) mf.style.width = Math.min(memPct,100) + '%';

  const kvCache = sys.kv_disk_cache || {};
  setText('kv-label', fmtBytes(kv.budget_bytes));
  setText('kv-total', 'Total ' + fmtBytes(kv.budget_bytes));
  setText('kv-path', kv.path ? pathBase(kv.path) : '--');
  setText('process-rss', 'RSS ' + fmtBytes(sys.process?.rss_bytes));
  const kvPct = numVal(kvCache.used_bytes) && numVal(kv.budget_bytes) ? Number(kvCache.used_bytes)/Number(kv.budget_bytes)*100 : 0;
  const kf = $('kv-fill');
  if (kf) kf.style.width = Math.min(kvPct,100) + '%';

  setText('cpu-usage', fmtPct(sys.cpu?.usage));
  setText('gpu-usage', fmtPct(sys.gpu?.usage));
  setText('cpu-temp', numVal(sys.cpu?.temperature) ? fmtNum(sys.cpu.temperature,0)+'°C' : '--');
  setText('gpu-temp', numVal(sys.gpu?.temperature) ? fmtNum(sys.gpu.temperature,0)+'°C' : '--');
  setText('process-id', status.pid ? 'PID ' + status.pid : '--');
  setText('uptime', fmtDur(telem.uptime_seconds || sys.uptime));

  // Charts
  updateCharts(telem, sys);

  // Model averages
  const {primary, best} = bestStats(status);
  setText('current-model-name', pathBase(status.config?.model || ''));
  setText('model-tok-s', fmtNum(avg(primary,'tok_s')));
  setText('model-prefill', fmtNum(avg(primary,'prefill_tokens_sec')));
  setText('model-latency', fmtNum(avg(primary,'latency_seconds')));
  setText('model-calls', fmtNum(primary?.count));
  const bestName = best?.name ? pathBase(best.name) : null;
  setText('model-summary', bestName ? `${bestName} ${fmtNum(best.tok_s)}t/s` : '--');
}

function updateCharts(telem, sys) {
  const tok = numVal(telem.tokens_sec);
  if (tok !== null) state.tokensHistory.push({t: Date.now(), v: tok});
  if (state.tokensHistory.length > MAX_POINTS) state.tokensHistory = state.tokensHistory.slice(-MAX_POINTS);

  const cpu = numVal(sys.cpu?.usage), gpu = numVal(sys.gpu?.usage);
  if (cpu !== null || gpu !== null) state.systemHistory.push({t: Date.now(), cpu, gpu});
  if (state.systemHistory.length > MAX_POINTS) state.systemHistory = state.systemHistory.slice(-MAX_POINTS);

  renderChart('tokens-chart', state.tokensHistory, {label:'tok/s', color:'#00ff41'});
  renderChart('system-chart', state.systemHistory, {cpu:'#00d4ff', gpu:'#ff9500'});
}

let charts = {};
function renderChart(canvasId, data, opts) {
  const canvas = $(canvasId);
  if (!canvas) return;
  if (!charts[canvasId]) {
    charts[canvasId] = new Chart(canvas, {
      type: 'line',
      data: { labels: [], datasets: [] },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { display: false, grid: { display: false } },
          y: { display: false, grid: { display: false } },
        },
        elements: { point: { radius: 0 }, line: { borderWidth: 1 } },
      },
    });
  }
  const chart = charts[canvasId];
  if (!chart) return;

  const labels = data.map(d => new Date(d.t).toLocaleTimeString());
  const datasets = canvasId === 'tokens-chart' ? [{
    label: opts.label, data: data.map(d => d.v),
    borderColor: opts.color, backgroundColor: opts.color + '20',
    fill: true, tension: 0.3,
  }] : [
    { label: 'CPU', data: data.map(d => d.cpu), borderColor: opts.cpu, backgroundColor: opts.cpu + '20', fill: true, tension: 0.3 },
    { label: 'GPU', data: data.map(d => d.gpu), borderColor: opts.gpu, backgroundColor: opts.gpu + '20', fill: true, tension: 0.3 },
  ];

  chart.data.labels = labels;
  chart.data.datasets = datasets;
  chart.update('none');
}

// ── Polling ──
async function poll() {
  try {
    const res = await fetch('/api/metrics');
    if (res.ok) updateStatus(await res.json());
  } catch (e) { /* ignore */ }
  setTimeout(poll, POLL_MS);
}
poll();

// ── Config ──
async function loadConfig() {
  const res = await fetch('/api/config');
  if (res.ok) state.config = await res.json();
  const sr = await fetch('/api/config-schema');
  if (sr.ok) state.schema = await sr.json();
  renderConfig();
}
function renderConfig() {
  const json = $('config-json');
  if (json) json.textContent = JSON.stringify(state.config || {}, null, 2);
  const count = $('schema-count');
  if (count) count.textContent = (state.schema ? Object.keys(state.schema).length : 0) + ' keys';
  const list = $('schema-list');
  if (!list) return;
  list.innerHTML = '';
  if (state.schema) {
    for (const [key, meta] of Object.entries(state.schema)) {
      const val = meta.current ?? meta.default;
      const overridden = meta.overridden;
      const div = document.createElement('div');
      div.className = 'schema-item' + (overridden ? ' overridden' : '');
      div.innerHTML = `<span style="color:var(--cyan)">${key}</span>: <span style="color:var(--text-dim)">${fmtVal(val)}</span>` +
        (overridden ? ' <span style="color:var(--amber);font-size:10px">[modified]</span>' : '');
      div.style.cursor = 'pointer';
      div.onclick = () => {
        const ek = $('config-edit-key'), ev = $('config-edit-value');
        if (ek && ev) { ek.value = key; ev.value = typeof val === 'object' ? JSON.stringify(val) : String(val); }
        const bar = $('schema-edit-bar');
        if (bar) bar.hidden = false;
      };
      list.appendChild(div);
    }
  }
}
$('refresh-config')?.addEventListener('click', loadConfig);
loadConfig();

$('config-save-btn')?.addEventListener('click', async () => {
  const key = $('config-edit-key')?.value?.trim();
  const val = $('config-edit-value')?.value?.trim();
  if (!key) return;
  let parsed = val;
  try { parsed = JSON.parse(val); } catch {}
  await fetch('/api/config', {
    method: 'PATCH',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({key, value: parsed}),
  });
  loadConfig();
});
$('config-apply-btn')?.addEventListener('click', async () => {
  const key = $('config-edit-key')?.value?.trim();
  const val = $('config-edit-value')?.value?.trim();
  if (!key) return;
  let parsed = val;
  try { parsed = JSON.parse(val); } catch {}
  const res = await fetch('/api/config/apply', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({key, value: parsed, restart: true}),
  });
  if (res.ok) {
    const data = await res.json();
    setText('restart-status', 'Restart triggered');
    setTimeout(() => setText('restart-status', ''), 5000);
  }
  loadConfig();
});
$('restart-ds4-btn')?.addEventListener('click', async () => {
  const res = await fetch('/api/restart', {method: 'POST'});
  if (res.ok) {
    setText('restart-status', 'Restart signal sent');
    setTimeout(() => setText('restart-status', ''), 5000);
  }
});

// ── Config Profiles ──
async function loadProfiles() {
  const res = await fetch('/api/config-profiles');
  if (!res.ok) return;
  const data = await res.json();
  state.configProfiles = data.profiles || [];
  renderProfiles();
  populateCompareSelects();
}
function renderProfiles() {
  const list = $('profiles-list');
  const count = $('profile-count');
  if (count) count.textContent = state.configProfiles.length;
  if (!list) return;
  if (!state.configProfiles.length) {
    list.innerHTML = '<div class="profiles-empty">No saved profiles.</div>';
    return;
  }
  list.innerHTML = state.configProfiles.map(p => `
    <div class="profile-card" data-id="${p.id}" onclick="toggleProfile('${p.id}')">
      <div class="profile-card-header">
        <strong>${p.label}</strong>
        ${p.active ? '<span class="profile-active">● active</span>' : ''}
      </div>
      ${p.description ? '<div class="profile-card-desc">'+p.description+'</div>' : ''}
      ${p.tags?.length ? '<div class="profile-card-tags">'+p.tags.map(t=>'<span>'+t+'</span>').join('')+'</div>' : ''}
      <div class="profile-card-actions">
        <button onclick="event.stopPropagation();applyProfile('${p.id}')">Apply</button>
        <button onclick="event.stopPropagation();downloadProfile('${p.id}')">Download</button>
        <button onclick="event.stopPropagation();deleteProfile('${p.id}')">Delete</button>
      </div>
    </div>
  `).join('');
}
async function toggleProfile(id) {
  if (state.expandedProfileId === id) { state.expandedProfileId = null; return; }
  state.expandedProfileId = id;
  if (!state.profileDetails[id]) {
    const res = await fetch(`/api/config-profiles/${id}`);
    if (res.ok) state.profileDetails[id] = await res.json();
  }
  renderProfiles();
  // Show details below expanded card
  const card = document.querySelector(`.profile-card[data-id="${id}"]`);
  if (card) {
    const detail = state.profileDetails[id];
    if (detail?.overrides) {
      const div = document.createElement('div');
      div.className = 'profile-card-desc';
      div.style.cssText = 'font-size:10px;color:var(--cyan);padding:4px 0';
      div.textContent = 'Overrides: ' + JSON.stringify(detail.overrides, null, 2);
      card.appendChild(div);
    }
  }
}
async function applyProfile(id) {
  const res = await fetch(`/api/config-profiles/${id}/apply`, {method: 'POST'});
  if (res.ok) {
    const data = await res.json();
    loadProfiles();
    loadConfig();
    setText('restart-status', data.result?.restart?.triggered ? 'Restarted' : 'Applied');
    setTimeout(() => setText('restart-status', ''), 5000);
  }
}
async function downloadProfile(id) {
  window.open(`/api/config-profiles/${id}/download`, '_blank');
}
async function deleteProfile(id) {
  await fetch(`/api/config-profiles/${id}`, {method: 'DELETE'});
  loadProfiles();
}
$('export-profile-btn')?.addEventListener('click', async (e) => {
  e.preventDefault();
  const label = $('profile-label-input')?.value?.trim();
  if (!label) return;
  const desc = $('profile-description-input')?.value?.trim();
  const tags = $('profile-tags-input')?.value?.trim();
  const res = await fetch('/api/config-profiles/export', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({label, description: desc, tags: tags ? tags.split(',').map(t=>t.trim()).filter(Boolean) : []}),
  });
  if (res.ok) {
    loadProfiles();
    $('profile-label-input').value = '';
    $('profile-description-input').value = '';
    $('profile-tags-input').value = '';
  }
});
$('import-profile-btn')?.addEventListener('click', () => $('profile-file-input')?.click());
$('profile-file-input')?.addEventListener('change', async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  await fetch('/api/config-profiles/import', {method: 'POST', body: form});
  loadProfiles();
});
loadProfiles();

function populateCompareSelects() {
  const selA = $('compare-config-a'), selB = $('compare-config-b');
  if (!selA || !selB) return;
  const opts = state.configProfiles.map(p =>
    `<option value="${p.id}">${p.label}</option>`
  ).join('');
  selA.innerHTML = '<option value="">Select A</option>' + opts;
  selB.innerHTML = '<option value="">Select B</option>' + opts;
}
$('compare-benchmarks')?.addEventListener('click', async () => {
  const a = $('compare-config-a')?.value, b = $('compare-config-b')?.value;
  const suite = $('compare-suite')?.value || 'quick_smoke';
  if (!a || !b || a === b) { setText('compare-status', 'Select two different configs.'); return; }
  state.compareRunning = true;
  setText('compare-status', 'Running comparison...');
  const res = await fetch('/api/benchmarks/compare', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({suite, iterations: 1, config_a: a, config_b: b}),
  });
  state.compareRunning = false;
  if (res.ok) {
    const data = await res.json();
    renderCompareResults(data);
    setText('compare-status', 'Done.');
  } else {
    setText('compare-status', 'Comparison failed.');
  }
});
function renderCompareResults(data) {
  const container = $('compare-results');
  if (!container) return;
  let html = '<div style="font-size:11px">';
  const diffs = data.diffs || {};
  for (const [key, diff] of Object.entries(diffs)) {
    if (diff.a == null || diff.b == null) continue;
    const arrow = diff.improved === true ? '↑' : diff.improved === false ? '↓' : '→';
    const color = diff.improved === true ? 'var(--green)' : diff.improved === false ? 'var(--red)' : 'var(--text-dim)';
    html += `<div><span style="color:var(--cyan)">${key}</span>: ${fmtNum(diff.a)} → ${fmtNum(diff.b)} <span style="color:${color}">${arrow} ${fmtNum(diff.delta)}</span></div>`;
  }
  html += '</div>';
  container.innerHTML = html;
}
async function loadBenchmarkSuites() {
  const res = await fetch('/api/benchmarks');
  if (!res.ok) return;
  const data = await res.json();
  state.benchmarkSuites = data.suites || [];
  populateBenchmarkSelects();
  // Load history
  const hr = await fetch('/api/benchmarks/history');
  if (hr.ok) {
    const hd = await hr.json();
    renderBenchmarkHistory(hd.history || []);
  }
}
function populateBenchmarkSelects() {
  const sel = $('benchmark-suite'), cmp = $('compare-suite');
  const opts = state.benchmarkSuites.map(s =>
    `<option value="${s.id || s}">${s.name || s.id || s}</option>`
  ).join('');
  if (sel) sel.innerHTML = opts;
  if (cmp) cmp.innerHTML = opts;
}
$('run-benchmark')?.addEventListener('click', async () => {
  const suite = $('benchmark-suite')?.value;
  const label = $('benchmark-label')?.value?.trim() || undefined;
  if (!suite) return;
  setText('benchmark-summary', 'running...');
  const res = await fetch('/api/benchmarks/run', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({suite_id: suite, compare_label: label}),
  });
  if (res.ok) {
    const data = await res.json();
    renderBenchmarkResults(data);
    loadBenchmarkSuites();
  }
  setText('benchmark-summary', 'idle');
});
function renderBenchmarkResults(data) {
  const container = $('bench-results');
  if (!container) return;
  let html = '<div style="font-size:11px">';
  const tasks = data.tasks || [];
  for (const task of tasks) {
    const passed = task.passed ? '<span style="color:var(--green)">PASS</span>' : '<span style="color:var(--red)">FAIL</span>';
    html += `<div>${task.title || task.task_id}: ${passed} score=${fmtNum(task.score)} tok/s=${fmtNum(task.tok_s)} latency=${fmtNum(task.latency_seconds)}s</div>`;
  }
  html += `<div style="color:var(--cyan);padding-top:4px">Avg: ${fmtNum(data.tok_s_avg)} tok/s | Pass rate: ${fmtPct(data.pass_rate)} | Duration: ${fmtDur(data.duration_seconds)}</div>`;
  html += '</div>';
  container.innerHTML = html;
}
function renderBenchmarkHistory(history) {
  const status = $('bench-history-status');
  if (status) status.textContent = history.length ? `${history.length} runs` : 'No history loaded.';
  if (!history.length) return;
  const canvas = $('benchmark-history-chart');
  if (!canvas) return;
  if (!state.benchmarkHistoryChart) {
    state.benchmarkHistoryChart = new Chart(canvas, {
      type: 'line',
      data: { labels: [], datasets: [] },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { display: false, grid: { display: false } },
          y: { display: false, grid: { display: false } },
        },
        elements: { point: { radius: 2 }, line: { borderWidth: 1 } },
      },
    });
  }
  const chart = state.benchmarkHistoryChart;
  const labels = history.map(h => h.label || h.compare_label || h.suite || h.run_id || '');
  const tokData = history.map(h => h.tok_s_avg || 0);
  chart.data.labels = labels;
  chart.data.datasets = [{
    label: 'tok/s',
    data: tokData,
    borderColor: '#00ff41',
    backgroundColor: '#00ff41' + '20',
    fill: true, tension: 0.3,
  }];
  chart.update('none');
}
loadBenchmarkSuites();

// ── Models ──
async function loadModels() {
  const res = await fetch('/api/models');
  if (!res.ok) return;
  const data = await res.json();
  state.models = data.models || [];
  const sel = $('model-select');
  if (sel) {
    sel.innerHTML = state.models.map(m =>
      `<option value="${m.path}">${m.name || pathBase(m.path)}${m.repo ? ' ('+m.repo+')' : ''}</option>`
    ).join('');
  }
  const descRes = await fetch('/api/model-descriptions');
  if (descRes.ok) state.modelDescriptions = await descRes.json();
}
$('model-select')?.addEventListener('change', () => {
  const sel = $('model-select');
  const desc = $('model-option-details');
  if (!sel || !desc) return;
  const path = sel.value;
  const model = state.models.find(m => m.path === path);
  desc.textContent = state.modelDescriptions[path] || model?.description || '';
});
$('switch-model-btn')?.addEventListener('click', async () => {
  const sel = $('model-select');
  if (!sel?.value) return;
  setText('model-summary', 'switching...');
  await fetch('/api/models/switch', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({model_path: sel.value, restart: true}),
  });
  setTimeout(() => loadModels(), 3000);
});
loadModels();

// ── MCP ──
async function loadMCP() {
  const res = await fetch('/api/mcp/manifest');
  if (!res.ok) return;
  const data = await res.json();
  const tools = $('mcp-tools'), resources = $('mcp-resources');
  if (tools) tools.innerHTML = (data.tools || []).map(t =>
    `<div style="padding:2px 0"><span style="color:var(--cyan)">${t.name}</span> ${t.description ? '— '+t.description : ''}</div>`
  ).join('');
  if (resources) resources.innerHTML = (data.resources || []).map(r =>
    `<div style="padding:2px 0"><span style="color:var(--green)">${r.uri}</span> ${r.description ? '— '+r.description : ''}</div>`
  ).join('');
}
loadMCP();
// Poll SSE state
async function pollSSE() {
  const res = await fetch('/api/mcp/resources');
  if (res.ok) setText('sse-state', 'SSE active');
  else setText('sse-state', 'SSE idle');
  setTimeout(pollSSE, 10000);
}
pollSSE();

// ── Update ──
$('update-check')?.addEventListener('click', async () => {
  const res = await fetch('/api/update/check');
  if (res.ok) {
    const data = await res.json();
    setText('update-result', data.latest?.tag_name ? `v${data.latest.tag_name} available` : 'Up to date');
  }
});
$('update-rollback')?.addEventListener('click', async () => {
  const res = await fetch('/api/update/rollback', {method: 'POST'});
  if (res.ok) setText('update-result', 'Rolled back');
});

// ── Chat ──
$('chat-send-btn')?.addEventListener('click', async () => {
  const input = $('chat-input');
  const msg = input?.value?.trim();
  if (!msg) return;
  const msgs = $('chat-messages');
  if (msgs) msgs.innerHTML += `<div style="color:var(--cyan)"><span style="color:var(--text-dim)">user:</span> ${msg}</div>`;
  input.value = '';
  try {
    const res = await fetch('/api/chat/completions', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({model:'default', messages:[{role:'user',content:msg}], max_tokens:512}),
    });
    if (res.ok) {
      const data = await res.json();
      const reply = data.choices?.[0]?.message?.content || '(no reply)';
      if (msgs) msgs.innerHTML += `<div><span style="color:var(--green)">ds4:</span> ${reply}</div>`;
      msgs.scrollTop = msgs.scrollHeight;
    } else {
      if (msgs) msgs.innerHTML += `<div style="color:var(--red)">DS4 not reachable.</div>`;
    }
  } catch {
    if (msgs) msgs.innerHTML += `<div style="color:var(--red)">Connection failed.</div>`;
  }
});

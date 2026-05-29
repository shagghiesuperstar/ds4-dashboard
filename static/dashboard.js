// Dwarfstar DS4 Dashboard — Live telemetry, config, benchmarks, MCP
// Cyberpunk green-on-dark white dwarf star theme

const POLL_MS = 2000;
const MAX_CHART_POINTS = 60;

const state = {
  config: null,
  schema: null,
  lastStatus: null,
  tokensHistory: [],
  systemHistory: [],
};

const $ = (id) => document.getElementById(id);

// ── Format Helpers ──────────────────────────────────────────

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined || Number.isNaN(Number(bytes))) return "--";
  const value = Number(bytes);
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let size = Math.abs(value);
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
  const signed = value < 0 ? -size : size;
  return `${signed.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function formatNumber(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `${formatNumber(value, 1)}%`;
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "--";
  const total = Math.max(0, Math.floor(Number(seconds)));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

function setText(id, value) {
  const node = $(id);
  if (node) node.textContent = value;
}

// ── Status Chip ─────────────────────────────────────────────

function setStateChip(status) {
  const chip = $("status-chip");
  const stateLabel = $("state-label");
  const currentState = status.state || (status.running ? "running" : "stopped");
  if (chip) chip.dataset.state = currentState;
  if (stateLabel) stateLabel.textContent = currentState.toUpperCase();
}

// ── Memory Gauge Color ─────────────────────────────────────

function setMemoryColor(fillEl, percent) {
  if (!fillEl) return;
  const pct = Number(percent);
  let color;
  if (pct < 70) color = "#00ff41";       // green
  else if (pct < 85) color = "#ffd700";   // yellow
  else color = "#ff003b";                 // red
  fillEl.style.background = `linear-gradient(90deg, ${color} 100%, #0a0a0a 100%)`;
}

// ── Main Render ─────────────────────────────────────────────

function renderStatus(status) {
  state.lastStatus = status;
  setStateChip(status);

  const config = status.config || state.config || {};
  const telemetry = status.telemetry || {};
  const kv = status.kv_cache || telemetry.kv_cache || config.kv_disk_cache || {};
  const system = status.system || {};
  const memory = system.memory || {};
  const cpu = system.cpu || {};
  const gpu = system.gpu || {};
  const temp = system.temperature || {};

  // Core metrics
  const tokens = telemetry.tok_s ?? telemetry.tokens_per_second ?? status.tok_s;
  setText("tokens-sec", tokens === undefined || tokens === null ? "--" : `${formatNumber(tokens, 2)} tok/s`);
  setText("prefill-sec", telemetry.prefill_s === undefined || telemetry.prefill_s === null ? "--" : `${formatNumber(telemetry.prefill_s, 2)} tok/s`);
  setText("context-window", config.context_window ? config.context_window.toLocaleString() : "--");
  setText("kv-cache", kv.used_bytes ? formatBytes(kv.used_bytes) : "--");
  setText("shader-count", String(config.metal?.shader_count ?? config_manager_metal_shaders ?? "--"));

  // Signal line
  setText("status-message", status.message || telemetry.message || "Telemetry online.");

  // Process / uptime
  setText("process-id", status.pid ? String(status.pid) : "--");
  setText("uptime", formatDuration(status.uptime_seconds ?? telemetry.uptime_seconds));

  // Memory gauge
  const usedPercent = memory.used_percent ?? memory.pressure_percent;
  const fill = $("memory-fill");
  if (fill && usedPercent !== undefined && usedPercent !== null) {
    const pct = Math.min(100, Math.max(0, Number(usedPercent)));
    fill.style.width = `${pct}%`;
    setMemoryColor(fill, pct);
  }
  setText("memory-used", memory.used_bytes ? formatBytes(memory.used_bytes) : formatPercent(usedPercent));
  setText("memory-free", memory.free_bytes ? formatBytes(memory.free_bytes) : "--");
  setText("swap-used", memory.swap_bytes ? formatBytes(memory.swap_bytes) : "--");
  setText("memory-pressure", memory.pressure || "--");

  // KV cache gauge
  const kvFill = $("kv-fill");
  const kvPct = kv.disk_fill_percent ?? kv.fill_percent;
  if (kvFill && kvPct !== undefined && kvPct !== null) {
    kvFill.style.width = `${Math.min(100, Math.max(0, Number(kvPct)))}%`;
  }
  setText("kv-label", kv.disk_used_bytes ? formatBytes(kv.disk_used_bytes) : formatMiB(kv.budget_mib));
  setText("kv-path", kv.path || "--");
  setText("process-rss", memory.ds4_rss_bytes ? formatBytes(memory.ds4_rss_bytes) : "--");

  // CPU / GPU / Temps
  const cpuText = cpu.usage_percent !== undefined && cpu.usage_percent !== null
    ? formatPercent(cpu.usage_percent)
    : cpu.load_average ? `load ${formatNumber(cpu.load_average[0], 2)}` : "--";
  setText("cpu-usage", cpuText);
  const gpuText = gpu.usage_percent !== undefined && gpu.usage_percent !== null
    ? formatPercent(gpu.usage_percent)
    : "--";
  setText("gpu-usage", gpuText);
  setText("cpu-temp", temp.cpu !== undefined && temp.cpu !== null ? `${formatNumber(temp.cpu, 1)}°C` : "--");
  setText("gpu-temp", temp.gpu !== undefined && temp.gpu !== null ? `${formatNumber(temp.gpu, 1)}°C` : "--");

  // Charts
  if (tokens !== undefined && tokens !== null) {
    state.tokensHistory.push({ t: Date.now(), v: Number(tokens) });
    if (state.tokensHistory.length > MAX_CHART_POINTS) state.tokensHistory = state.tokensHistory.slice(-MAX_CHART_POINTS);
  }
  if (cpuText !== "--" && gpuText !== "--") {
    state.systemHistory.push({
      t: Date.now(),
      cpu: Number(cpu.usage_percent),
      gpu: Number(gpu.usage_percent),
      temp_cpu: Number(temp.cpu),
      temp_gpu: Number(temp.gpu),
    });
    if (state.systemHistory.length > MAX_CHART_POINTS) state.systemHistory = state.systemHistory.slice(-MAX_CHART_POINTS);
  }

  drawTokensChart();
  drawSystemChart();

  // Animate logo based on KV fill
  const logo = document.querySelector(".dwarfstar-logo");
  if (logo && kvPct !== undefined && kvPct !== null) {
    logo.dataset.state = status.state || "unknown";
    logo.style.setProperty("--kv-distortion", String(kvPct));
  }
}

// ── Charts ──────────────────────────────────────────────────

function drawTokensChart() {
  const canvas = $("tokens-chart");
  if (!canvas || state.tokensHistory.length < 2) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const data = state.tokensHistory;
  const maxV = Math.max(...data.map(d => d.v)) * 1.1 || 1;
  const minV = 0;

  // Grid
  ctx.strokeStyle = "#00ff4133";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = h - 10 - (i / 4) * (h - 20);
    ctx.beginPath(); ctx.moveTo(10, y); ctx.lineTo(w - 10, y); ctx.stroke();
    const val = minV + (maxV - minV) * (i / 4);
    ctx.fillStyle = "#00ff4188";
    ctx.font = "9px monospace";
    ctx.fillText(Math.round(val) + " tok/s", 4, y - 2);
  }

  // Line
  ctx.beginPath();
  ctx.strokeStyle = "#00ff41";
  ctx.lineWidth = 2;
  for (let i = 0; i < data.length; i++) {
    const x = 10 + (i / (data.length - 1)) * (w - 20);
    const y = h - 10 - ((data[i].v - minV) / (maxV - minV)) * (h - 20);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Fill
  ctx.lineTo(w - 10, h - 10);
  ctx.lineTo(10, h - 10);
  ctx.closePath();
  ctx.fillStyle = "#00ff4118";
  ctx.fill();
}

function drawSystemChart() {
  const canvas = $("system-chart");
  if (!canvas || state.systemHistory.length < 2) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const data = state.systemHistory;
  const maxPct = Math.max(100, ...data.map(d => Math.max(d.cpu, d.gpu))) * 1.1;

  // Grid
  ctx.strokeStyle = "#00ff4133";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = h - 10 - (i / 4) * (h - 20);
    ctx.beginPath(); ctx.moveTo(10, y); ctx.lineTo(w - 10, y); ctx.stroke();
    ctx.fillStyle = "#00ff4188";
    ctx.font = "9px monospace";
    ctx.fillText(Math.round(maxPct * (i / 4)) + "%", 4, y - 2);
  }

  // CPU line (green)
  ctx.beginPath();
  ctx.strokeStyle = "#00ff41";
  ctx.lineWidth = 2;
  for (let i = 0; i < data.length; i++) {
    const x = 10 + (i / (data.length - 1)) * (w - 20);
    const y = h - 10 - (data[i].cpu / maxPct) * (h - 20);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.stroke();

  // GPU line (cyan)
  ctx.beginPath();
  ctx.strokeStyle = "#00d4ff";
  ctx.lineWidth = 2;
  for (let i = 0; i < data.length; i++) {
    const x = 10 + (i / (data.length - 1)) * (w - 20);
    const y = h - 10 - (data[i].gpu / maxPct) * (h - 20);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Legend
  ctx.fillStyle = "#00ff41";
  ctx.font = "9px monospace";
  ctx.fillText("CPU", w - 40, 14);
  ctx.fillStyle = "#00d4ff";
  ctx.fillText("GPU", w - 40, 26);
}

// ── JSON Syntax Highlight ──────────────────────────────────

function syntaxHighlight(json) {
  const escaped = json.replace(/[&<>]/g, (char) => ({ "&": "&", "<": "<", ">": ">" }[char]));
  return escaped.replace(
    /("(?:\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
    (match) => {
      let cls = "json-number";
      if (match.startsWith('"')) cls = match.endsWith(":") ? "json-key" : "json-string";
      else if (match === "true" || match === "false") cls = "json-boolean";
      else if (match === "null") cls = "json-null";
      return `<span class="${cls}">${match}</span>`;
    },
  );
}

// ── Config Render ───────────────────────────────────────────

function renderConfig(config) {
  state.config = config;
  const json = JSON.stringify(config, null, 2);
  const viewer = $("config-json");
  if (viewer) viewer.innerHTML = syntaxHighlight(json);
}

function renderSchema(schema) {
  state.schema = schema;
  const entries = Object.entries(schema || {});
  setText("schema-count", `${entries.length} keys`);
  const list = $("schema-list");
  if (!list) return;
  list.replaceChildren();
  for (const [key, meta] of entries) {
    const item = document.createElement("article");
    item.className = "schema-item";

    const title = document.createElement("div");
    title.className = "schema-title";
    const name = document.createElement("strong");
    name.textContent = key;
    const type = document.createElement("span");
    type.textContent = meta.type || "unknown";
    title.append(name, type);

    const desc = document.createElement("p");
    desc.textContent = meta.desc || "No description available.";

    const fallback = document.createElement("code");
    fallback.textContent = String(meta.default ?? "");

    item.append(title, desc, fallback);
    item.tabIndex = 0;
    item.classList.add("editable");
    item.addEventListener("click", () => {
      $("config-edit-key").value = key;
      $("config-edit-value").value = String(meta.default ?? "");
      $("schema-editor-bar").style.display = "flex";
      $("config-edit-value").focus();
    });
    list.append(item);
  }
}

// ── Config Save ─────────────────────────────────────────────

async function saveConfig() {
  const key = $("config-edit-key").value.trim();
  const value = $("config-edit-value").value.trim();
  if (!key) return;
  try {
    const result = await fetch("/api/config", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value }),
    });
    if (!result.ok) throw new Error(`HTTP ${result.status}`);
    const data = await result.json();
    $("config-edit-key").value = "";
    $("config-edit-value").value = "";
    $("schema-editor-bar").style.display = "none";
    await refreshConfig();
    setText("status-message", `Config updated: ${data.key} = ${data.value}`);
  } catch (error) {
    setText("status-message", `Config save error: ${error.message}`);
  }
}

// ── Benchmarks ──────────────────────────────────────────────

async function refreshBenchmarks() {
  try {
    const data = await fetchJson("/api/benchmarks");
    const select = $("benchmark-suite");
    if (!select) return;
    select.replaceChildren();
    for (const suite of (data.suites || [])) {
      const opt = document.createElement("option");
      opt.value = suite.id;
      opt.textContent = `${suite.name} (${suite.benchmark_count} benchmarks)`;
      select.append(opt);
    }
    const last = data.last_results;
    if (last) renderBenchmarkResults(last);
  } catch (error) {
    console.warn("Benchmarks refresh error:", error.message);
  }
}

function renderBenchmarkResults(results) {
  const container = $("benchmark-results");
  if (!container) return;
  let html = "";
  if (Array.isArray(results)) {
    for (const r of results) {
      html += `<div class="benchmark-row">
        <strong>${r.label || r.suite_id || "result"}</strong>
        <span class="benchmark-stat">${r.status || "done"}</span>
        <span class="benchmark-stat">${r.tok_s !== undefined ? formatNumber(r.tok_s, 2) + " tok/s" : ""}</span>
        <span class="benchmark-stat">${r.pass_rate !== undefined ? formatPercent(r.pass_rate) : ""}</span>
        <span class="benchmark-stat">${r.p50_ms !== undefined ? r.p50_ms.toFixed(0) + "ms" : ""}</span>
      </div>`;
    }
  } else if (results.suites) {
    for (const [id, r] of Object.entries(results.suites)) {
      html += `<div class="benchmark-row">
        <strong>${id}</strong>
        <span class="benchmark-stat">${r.status || "done"}</span>
        <span class="benchmark-stat">${r.tok_s !== undefined ? formatNumber(r.tok_s, 2) + " tok/s" : ""}</span>
      </div>`;
    }
  } else {
    html = `<div class="benchmark-row">${JSON.stringify(results, null, 2)}</div>`;
  }
  container.innerHTML = html;
  setText("benchmark-summary", results.status || "done");
}

async function runBenchmark() {
  const suiteId = $("benchmark-suite")?.value || "quick_smoke";
  const label = $("benchmark-label")?.value || "";
  try {
    const result = await fetch("/api/benchmarks/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suite_id: suiteId, compare_label: label || null, iterations: 1 }),
    });
    if (!result.ok) throw new Error(`HTTP ${result.status}`);
    const data = await result.json();
    renderBenchmarkResults(data);
    setText("status-message", `Benchmark ${suiteId} completed.`);
  } catch (error) {
    setText("status-message", `Benchmark error: ${error.message}`);
  }
}

// ── Update ──────────────────────────────────────────────────

async function checkUpdate() {
  try {
    const data = await fetchJson("/api/update/check");
    if (data.ok && data.tag_name) {
      setText("update-result", `${data.tag_name} (${data.name})`);
    } else if (data.ok && data.dry_run) {
      setText("update-result", data.message || "No update available.");
    } else {
      setText("update-result", data.error || "Check failed.");
    }
  } catch (error) {
    setText("update-result", `Error: ${error.message}`);
  }
}

// ── MCP Manifest ────────────────────────────────────────────

async function refreshMCP() {
  try {
    const data = await fetchJson("/api/mcp/manifest");
    const toolsDiv = $("mcp-tools");
    if (toolsDiv) {
      toolsDiv.replaceChildren();
      for (const tool of (data.tools || [])) {
        const el = document.createElement("div");
        el.className = "mcp-item";
        el.innerHTML = `<strong>${tool.name}</strong> <span>${tool.description}</span>`;
        toolsDiv.append(el);
      }
    }
    const resourcesDiv = $("mcp-resources");
    if (resourcesDiv) {
      resourcesDiv.replaceChildren();
      for (const res of (data.resources || [])) {
        const el = document.createElement("div");
        el.className = "mcp-item";
        el.innerHTML = `<strong>${res.uri}</strong> <span>${res.description}</span>`;
        resourcesDiv.append(el);
      }
    }
  } catch (error) {
    console.warn("MCP manifest refresh error:", error.message);
  }
}

// ── Fetch ───────────────────────────────────────────────────

async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

async function refreshConfig() {
  const [config, schema] = await Promise.all([
    fetchJson("/api/config"),
    fetchJson("/api/config-schema"),
  ]);
  renderConfig(config);
  renderSchema(schema);
}

async function refreshStatus() {
  try {
    const status = await fetchJson("/api/status");
    renderStatus(status);
  } catch (error) {
    renderStatus({
      state: "error",
      running: false,
      message: error.message,
      config: state.config,
    });
  }
}

// ── Boot ────────────────────────────────────────────────────

async function boot() {
  // Event handlers
  $("refresh-config")?.addEventListener("click", () => {
    refreshConfig().catch((error) => setText("status-message", error.message));
  });
  $("config-save-btn")?.addEventListener("click", () => {
    saveConfig().catch((error) => setText("status-message", error.message));
  });
  $("run-benchmark")?.addEventListener("click", () => {
    runBenchmark().catch((error) => setText("status-message", error.message));
  });
  $("update-check")?.addEventListener("click", () => {
    checkUpdate().catch((error) => setText("status-message", error.message));
  });

  // Initial loads
  await Promise.all([
    refreshConfig().catch((error) => setText("status-message", error.message)),
    refreshBenchmarks().catch((error) => console.warn("benchmarks:", error.message)),
    refreshMCP().catch((error) => console.warn("mcp:", error.message)),
  ]);

  // Start telemetry polling
  await refreshStatus();
  window.setInterval(refreshStatus, POLL_MS);
}

boot();

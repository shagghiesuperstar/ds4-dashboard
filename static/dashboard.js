// Dwarfstar DS4 Dashboard — Live telemetry, config, benchmarks, MCP
// Cyberpunk green-on-dark white dwarf star theme

const POLL_MS = 2000;
const MAX_CHART_POINTS = 60;

const state = {
  config: null,
  schema: null,
  lastStatus: null,
  benchmarkSuites: [],
  models: [],
  compareProfiles: [],
  tokensHistory: [],
  systemHistory: [],
  benchmarkHistoryChart: null,
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

function formatMiB(mib) {
  if (mib === null || mib === undefined || Number.isNaN(Number(mib))) return "--";
  return formatBytes(Number(mib) * 1024 * 1024);
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
  const rawState = status.state || (status.running ? "running" : "stopped");
  const labelMap = { running: "RUNNING", stopped: "OFFLINE", error: "ERROR", unknown: "UNKNOWN" };
  const displayLabel = labelMap[rawState] || rawState.toUpperCase();
  if (chip) chip.dataset.state = rawState;
  if (stateLabel) stateLabel.textContent = displayLabel;
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
  setText("kv-cache", kv.used_bytes ? formatBytes(kv.used_bytes) : kv.budget_mib ? `budget ${formatMiB(kv.budget_mib)}` : "--");
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
  setText("memory-total", memory.total_bytes ? "Total " + formatBytes(memory.total_bytes) : "--");
  setText("memory-free", memory.free_bytes ? "Free " + formatBytes(memory.free_bytes) : "--");
  setText("swap-used", memory.swap?.used_bytes ? formatBytes(memory.swap.used_bytes) + " swap" : "--");
  setText("memory-pressure", memory.pressure || "--");

  // KV cache gauge
  const kvFill = $("kv-fill");
  const kvPct = kv.disk_fill_percent ?? kv.fill_percent;
  if (kvFill && kvPct !== undefined && kvPct !== null) {
    kvFill.style.width = `${Math.min(100, Math.max(0, Number(kvPct)))}%`;
  } else if (kvFill) {
    kvFill.style.width = "0%";
  }
  // Show used / budget for KV cache
  const kvUsed = kv.disk_used_bytes || kv.used_bytes;
  const kvBudget = kv.budget_bytes || (kv.budget_mib ? Number(kv.budget_mib) * 1024 * 1024 : null);
  if (kvUsed) {
    setText("kv-label", `${formatBytes(kvUsed)} / ${formatBytes(kvBudget)}`);
  } else if (kvBudget) {
    setText("kv-label", `budget: ${formatBytes(kvBudget)}`);
  } else {
    setText("kv-label", "--");
  }
  const kvTotal = kv.budget_bytes || kv.total_bytes;
  setText("kv-total", kvTotal ? "Total " + formatBytes(kvTotal) : "--");
  setText("kv-path", kv.path || "--");
  setText("process-rss", memory.ds4_rss_bytes ? formatBytes(memory.ds4_rss_bytes) : "--");

  // CPU / GPU / Temps
  const cpuPct = cpu.usage_percent;
  const gpuPct = gpu.usage_percent;
  const cpuTemp = temp.cpu;
  const gpuTempVal = temp.gpu;

  const cpuText = cpuPct !== undefined && cpuPct !== null
    ? formatPercent(cpuPct)
    : cpu.load_average ? `load ${formatNumber(cpu.load_average[0], 2)}` : "N/A";
  setText("cpu-usage", cpuText);
  const gpuText = gpuPct !== undefined && gpuPct !== null
    ? formatPercent(gpuPct)
    : gpu.source === "unavailable" ? "N/A" : "--";
  setText("gpu-usage", gpuText);
  setText("cpu-temp", cpuTemp !== undefined && cpuTemp !== null ? `${formatNumber(cpuTemp, 1)}°C` : "N/A");
  setText("gpu-temp", gpuTempVal !== undefined && gpuTempVal !== null ? `${formatNumber(gpuTempVal, 1)}°C` : "N/A");

  // Per-model running averages
  const modelAvg = status.model_averages || {};
  if (modelAvg.count > 0) {
    const tok = modelAvg.tok_s || {};
    const prefill = modelAvg.prefill_tok_s || {};
    const lat = modelAvg.latency_seconds || {};
    setText("model-tok-s", tok.avg !== null ? `${formatNumber(tok.avg, 2)} tok/s` : "--");
    setText("model-prefill", prefill.avg !== null ? `${formatNumber(prefill.avg, 2)} tok/s` : "--");
    setText("model-latency", lat.avg !== null ? `${(lat.avg * 1000).toFixed(0)}ms` : "--");
    setText("model-calls", String(modelAvg.total_calls ?? "--"));
    setText("model-summary", `${modelAvg.total_calls} calls | ${modelAvg.window_size} window`);
  } else {
    setText("model-tok-s", "--");
    setText("model-prefill", "--");
    setText("model-latency", "--");
    setText("model-calls", "--");
    setText("model-summary", "no data yet");
  }
  const configModel = status.config?.model?.path || status.config?.model || "";
  setText("current-model-name", typeof configModel === "string" ? configModel.split("/").pop() : "--");

  // Charts
  if (tokens !== undefined && tokens !== null) {
    state.tokensHistory.push({ t: Date.now(), v: Number(tokens) });
    if (state.tokensHistory.length > MAX_CHART_POINTS) state.tokensHistory = state.tokensHistory.slice(-MAX_CHART_POINTS);
  }
  // Push system history only when both CPU and GPU have valid numeric values
  const cpuNum = cpuPct !== undefined && cpuPct !== null ? Number(cpuPct) : null;
  const gpuNum = gpuPct !== undefined && gpuPct !== null ? Number(gpuPct) : null;
  const cpuTempNum = cpuTemp !== undefined && cpuTemp !== null ? Number(cpuTemp) : null;
  const gpuTempNum = gpuTempVal !== undefined && gpuTempVal !== null ? Number(gpuTempVal) : null;
  if (cpuNum !== null && !Number.isNaN(cpuNum) && gpuNum !== null && !Number.isNaN(gpuNum)) {
    state.systemHistory.push({
      t: Date.now(),
      cpu: cpuNum,
      gpu: gpuNum,
      temp_cpu: cpuTempNum,
      temp_gpu: gpuTempNum,
    });
    if (state.systemHistory.length > MAX_CHART_POINTS) state.systemHistory = state.systemHistory.slice(-MAX_CHART_POINTS);
  }

  drawTokensChart();
  drawSystemChart();

  // Animate logo based on KV fill and live throughput
  const logo = document.querySelector(".dwarfstar-logo");
  if (logo) {
    logo.dataset.state = status.state || "unknown";
    if (kvPct !== undefined && kvPct !== null) {
      logo.style.setProperty("--kv-distortion", String(kvPct));
    }
    const tokenRate = Number(tokens);
    if (!Number.isNaN(tokenRate) && tokenRate > 0) {
      const pulseSeconds = Math.max(0.45, Math.min(2.4, 2.35 - Math.log10(tokenRate + 1) * 0.55));
      logo.style.setProperty("--tok-pulse-duration", `${pulseSeconds.toFixed(2)}s`);
      logo.style.setProperty("--tok-star-drift", String(Math.min(36, tokenRate / 2)));
    }
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
  const escaped = json.replace(/[&<>]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[char]));
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

  // Update endpoint pill from live config
  const host = config.primary_host || "127.0.0.1";
  const port = config.primary_port || config.port || "8001";
  const pill = $("endpoint-pill");
  if (pill) pill.textContent = `${host}:${port}`;
  buildCompareProfiles();
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
    if (meta.overridden) item.classList.add("overridden");

    const title = document.createElement("div");
    title.className = "schema-title";
    const name = document.createElement("strong");
    name.textContent = key;
    const type = document.createElement("span");
    type.textContent = meta.type || "unknown";
    title.append(name, type);

    // Show current and default inline in description
    const currentVal = meta.current !== undefined ? meta.current : meta.default;
    const defaultValue = meta.default;
    const fmtVal = (v) => {
      if (v === null || v === undefined) return "—";
      const s = String(v);
      return s === "" ? "—" : s;
    };
    const desc = document.createElement("p");
    desc.textContent = `${meta.desc || "No description available."} (current: ${fmtVal(currentVal)}, default: ${fmtVal(defaultValue)})`;

    // Also show as separate styled code elements for quick scanning
    const valuesDiv = document.createElement("div");
    valuesDiv.className = "schema-values";

    const currentDisplay = document.createElement("code");
    currentDisplay.className = "schema-current";
    currentDisplay.textContent = `current: ${fmtVal(currentVal)}`;

    const defaultDisplay = document.createElement("code");
    defaultDisplay.className = "schema-default";
    defaultDisplay.textContent = `default: ${fmtVal(defaultValue)}`;

    valuesDiv.append(currentDisplay, defaultDisplay);

    item.append(title, desc, valuesDiv);
    item.tabIndex = 0;
    item.classList.add("editable");
    item.addEventListener("click", () => {
      $("config-edit-key").value = key;
      $("config-edit-value").value = String(currentVal ?? "");
      $("schema-editor-bar").style.display = "flex";
      $("config-edit-value").focus();
    });
    list.append(item);
  }
  buildCompareProfiles();
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
    const restartNeeded = data.updated?.restart_needed;
    const msg = `Config updated: ${data.updated?.key} = ${data.updated?.value}`;
    setText("status-message", restartNeeded ? `${msg} (restart needed)` : msg);
  } catch (error) {
    setText("status-message", `Config save error: ${error.message}`);
  }
}

async function applyConfig() {
  const key = $("config-edit-key").value.trim();
  const value = $("config-edit-value").value.trim();
  if (!key) return;
  setText("restart-status", "Applying + restarting...");
  try {
    const result = await fetch("/api/config/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value }),
    });
    if (!result.ok) throw new Error(`HTTP ${result.status}`);
    const data = await result.json();
    $("config-edit-key").value = "";
    $("config-edit-value").value = "";
    $("schema-editor-bar").style.display = "none";
    await refreshConfig();
    const r = data.result?.restart || {};
    if (r.triggered && r.exit_code === 0) {
      setText("restart-status", "DS4 restarted successfully.");
    } else if (r.triggered && r.exit_code !== 0) {
      setText("restart-status", `Restart exit ${r.exit_code}: ${r.stderr || r.stdout || ""}`);
    } else {
      setText("restart-status", "No restart needed — override applied.");
    }
    setText("status-message", `Applied: ${data.result?.key} = ${data.result?.value}`);
  } catch (error) {
    setText("restart-status", `Error: ${error.message}`);
    setText("status-message", `Apply error: ${error.message}`);
  }
}

async function restartDS4() {
  setText("restart-status", "Restarting DS4...");
  try {
    const result = await fetch("/api/restart", { method: "POST" });
    if (!result.ok) throw new Error(`HTTP ${result.status}`);
    const data = await result.json();
    if (data.ok) {
      setText("restart-status", "DS4 restarted successfully.");
    } else {
      setText("restart-status", `Restart failed: ${data.error || `exit ${data.exit_code}`}`);
    }
  } catch (error) {
    setText("restart-status", `Error: ${error.message}`);
  }
}

// ── Benchmarks ──────────────────────────────────────────────

function buildCompareProfiles() {
  const profiles = [];
  profiles.push({ id: "current", label: "Current config", overrides: {} });

  const schemaDefaults = {};
  for (const [key, meta] of Object.entries(state.schema || {})) {
    if (meta.default !== undefined && meta.default !== null) schemaDefaults[key] = meta.default;
  }
  if (Object.keys(schemaDefaults).length > 0) {
    profiles.push({ id: "defaults", label: "Dashboard defaults", overrides: schemaDefaults });
  }

  const currentModel = state.config?.model?.path || state.config?.model || "";
  if (typeof currentModel === "string" && currentModel) {
    profiles.push({
      id: `current-model:${currentModel}`,
      label: `Current model: ${currentModel.split("/").pop()}`,
      overrides: { model: currentModel },
    });
  }

  for (const model of state.models || []) {
    if (!model.path) continue;
    profiles.push({
      id: `model:${model.path}`,
      label: `Model: ${model.filename || model.path.split("/").pop()}`,
      overrides: { model: model.path },
    });
  }

  const seen = new Set();
  state.compareProfiles = profiles.filter((profile) => {
    const key = `${profile.id}:${JSON.stringify(profile.overrides)}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  renderCompareProfileOptions();
}

function renderCompareProfileOptions() {
  const aSelect = $("compare-config-a");
  const bSelect = $("compare-config-b");
  if (!aSelect || !bSelect) return;

  const previousA = aSelect.value;
  const previousB = bSelect.value;
  for (const select of [aSelect, bSelect]) {
    select.replaceChildren();
    for (const profile of state.compareProfiles) {
      const opt = document.createElement("option");
      opt.value = profile.id;
      opt.textContent = profile.label;
      select.append(opt);
    }
  }
  if (state.compareProfiles.some((profile) => profile.id === previousA)) aSelect.value = previousA;
  if (state.compareProfiles.some((profile) => profile.id === previousB)) bSelect.value = previousB;
  if (!bSelect.value && state.compareProfiles.length > 1) bSelect.value = state.compareProfiles[1].id;
  if (aSelect.value === bSelect.value && state.compareProfiles.length > 1) bSelect.value = state.compareProfiles[1].id;
}

function selectedCompareProfile(id) {
  return state.compareProfiles.find((profile) => profile.id === id) || null;
}

async function refreshBenchmarks() {
  try {
    const data = await fetchJson("/api/benchmarks");
    state.benchmarkSuites = data.suites || [];
    const runSelect = $("benchmark-suite");
    const compareSelect = $("compare-suite");
    for (const select of [runSelect, compareSelect]) {
      if (!select) continue;
      select.replaceChildren();
      for (const suite of state.benchmarkSuites) {
        const opt = document.createElement("option");
        opt.value = suite.id;
        opt.textContent = `${suite.name} (${suite.task_count} tasks)`;
        select.append(opt);
      }
    }
    if (!runSelect && !compareSelect) return;
    for (const suite of (data.suites || [])) {
      if (suite.id === "quick_smoke" || suite.id === "smoke") {
        if (runSelect) runSelect.value = suite.id;
        if (compareSelect) compareSelect.value = suite.id;
        break;
      }
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
    // Array of run results from last_results
    for (const r of results) {
      html += `<div class="benchmark-row">
        <strong>${r.label || r.suite_id || "result"}</strong>
        <span class="benchmark-stat">${r.status || "done"}</span>
        <span class="benchmark-stat">${r.tok_s !== undefined ? formatNumber(r.tok_s, 2) + " tok/s" : ""}</span>
        <span class="benchmark-stat">${r.pass_rate !== undefined ? formatPercent(r.pass_rate) : ""}</span>
        <span class="benchmark-stat">${r.p50_ms !== undefined ? r.p50_ms.toFixed(0) + "ms" : ""}</span>
      </div>`;
    }
  } else if (results.run_id) {
    // Single run result from /api/benchmarks/run
    const r = results;
    const p50 = r.latency_p50_seconds ? (r.latency_p50_seconds * 1000).toFixed(0) + "ms" : "";
    const p95 = r.latency_p95_seconds ? (r.latency_p95_seconds * 1000).toFixed(0) + "ms" : "";
    html += `<div class="benchmark-row">
      <strong>${r.suite_name || r.suite_id}</strong>
      <span class="benchmark-stat">${r.pass_count}/${r.task_count} passed</span>
      <span class="benchmark-stat">${r.pass_rate !== undefined ? formatPercent(r.pass_rate) : ""}</span>
      <span class="benchmark-stat">${r.tok_s_avg !== undefined && r.tok_s_avg !== null ? formatNumber(r.tok_s_avg, 2) + " tok/s" : ""}</span>
      <span class="benchmark-stat">${p95 ? `p95 ${p95}` : ""}</span>
      <span class="benchmark-stat">${p50 ? `p50 ${p50}` : ""}</span>
    </div>`;
    // Per-task breakdown
    if (r.tasks && Array.isArray(r.tasks)) {
      for (const t of r.tasks) {
        const status = t.passed ? "✅" : t.error ? "❌" : "⚠️";
        html += `<div class="benchmark-task">
          <span>${status}</span>
          <span class="benchmark-task-name">${t.title}</span>
          <span class="benchmark-stat">${t.score !== undefined ? (t.score * 100).toFixed(0) + "%" : ""}</span>
          <span class="benchmark-stat">${t.tok_s !== undefined && t.tok_s !== null ? formatNumber(t.tok_s, 2) + " tok/s" : ""}</span>
          <span class="benchmark-stat">${t.error ? t.error : ""}</span>
        </div>`;
      }
    }
  } else if (results.suites) {
    // Suites list from /api/benchmarks — show suite names
    for (const suite of results.suites) {
      html += `<div class="benchmark-row">
        <strong>${suite.name || suite.id}</strong>
        <span class="benchmark-stat">${suite.task_count} tasks</span>
        <span class="benchmark-stat">${suite.description ? suite.description.slice(0, 60) : ""}</span>
      </div>`;
    }
    // Also show last_results inline
    if (results.last_results && Array.isArray(results.last_results)) {
      renderBenchmarkResults(results.last_results);
      return;
    }
  } else {
    html = `<div class="benchmark-row">${JSON.stringify(results, null, 2)}</div>`;
  }
  container.innerHTML = html;
  setText("benchmark-summary", results.status || "done");
}

async function renderBenchmarkHistory() {
  const canvas = $("benchmark-history-chart");
  if (!canvas) return;

  const status = $("benchmark-history-status");
  let payload;
  try {
    payload = await fetchJson("/api/benchmarks/history");
  } catch (error) {
    if (status) status.textContent = `History error: ${error.message}`;
    return;
  }

  const history = Array.isArray(payload) ? payload : payload.history || [];
  const rows = history
    .map((entry) => ({
      ...entry,
      label: entry.label || entry.suite_name || entry.suite || "Benchmark",
      timestampMs: Date.parse(entry.timestamp),
      tokValue: entry.tok_s === null || entry.tok_s === undefined ? null : Number(entry.tok_s),
    }))
    .filter((entry) => Number.isFinite(entry.timestampMs) && Number.isFinite(entry.tokValue))
    .sort((a, b) => a.timestampMs - b.timestampMs);

  if (!rows.length) {
    if (status) status.textContent = "No benchmark history yet.";
    if (state.benchmarkHistoryChart) {
      state.benchmarkHistoryChart.destroy();
      state.benchmarkHistoryChart = null;
    }
    return;
  }
  if (typeof Chart === "undefined") {
    if (status) status.textContent = "Chart.js unavailable.";
    return;
  }

  const labels = rows.map((row) => new Date(row.timestampMs).toLocaleString());
  const suiteLabels = [...new Set(rows.map((row) => row.label))];
  const palette = ["#00ff41", "#00d4ff", "#ff9500", "#ff003b", "#dffaff", "#a6ff00"];
  const datasets = suiteLabels.map((label, index) => ({
    label,
    data: rows.map((row) => (row.label === label ? row.tokValue : null)),
    historyRows: rows.map((row) => (row.label === label ? row : null)),
    borderColor: palette[index % palette.length],
    backgroundColor: `${palette[index % palette.length]}22`,
    pointRadius: 3,
    pointHoverRadius: 5,
    spanGaps: true,
    tension: 0.25,
  }));

  if (state.benchmarkHistoryChart) state.benchmarkHistoryChart.destroy();
  state.benchmarkHistoryChart = new Chart(canvas, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "nearest", intersect: false },
      scales: {
        x: {
          ticks: { color: "#808080", maxRotation: 35, minRotation: 0 },
          grid: { color: "#00ff4118" },
        },
        y: {
          beginAtZero: true,
          title: { display: true, text: "tok/s", color: "#808080" },
          ticks: { color: "#808080" },
          grid: { color: "#00ff4118" },
        },
      },
      plugins: {
        legend: { labels: { color: "#e0e0e0" } },
        tooltip: {
          callbacks: {
            title(items) {
              const point = items[0];
              const row = point?.dataset?.historyRows?.[point.dataIndex];
              return row ? new Date(row.timestampMs).toLocaleString() : point?.label || "";
            },
            label(context) {
              const row = context.dataset.historyRows?.[context.dataIndex] || {};
              const suite = row.suite_name || row.suite || context.dataset.label;
              const pass = row.pass_rate === undefined || row.pass_rate === null ? "--" : formatPercent(row.pass_rate);
              const tok = context.parsed.y === null || context.parsed.y === undefined ? "--" : `${formatNumber(context.parsed.y, 2)} tok/s`;
              return `${suite}: ${tok}, pass ${pass}`;
            },
          },
        },
      },
    },
  });

  if (status) status.textContent = `${rows.length} runs`;
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
    await renderBenchmarkHistory();
    setText("status-message", `Benchmark ${suiteId} completed.`);
  } catch (error) {
    setText("status-message", `Benchmark error: ${error.message}`);
  }
}

// ── Benchmark Compare ────────────────────────────────────────

async function compareBenchmarks() {
  const suite = $("compare-suite")?.value || $("benchmark-suite")?.value || "quick_smoke";
  const configA = selectedCompareProfile($("compare-config-a")?.value);
  const configB = selectedCompareProfile($("compare-config-b")?.value);
  if (!configA || !configB) {
    setText("status-message", "Select both benchmark configs before comparing.");
    return;
  }
  if (configA.id === configB.id) {
    setText("status-message", "Choose two different configs for compare mode.");
    return;
  }

  setText("benchmark-summary", "comparing");
  setText("status-message", `Running ${suite} against ${configA.label} and ${configB.label}...`);
  try {
    const result = await fetch("/api/benchmarks/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suite, config_a: configA, config_b: configB, iterations: 1 }),
    });
    if (!result.ok) throw new Error(`HTTP ${result.status}`);
    const data = await result.json();
    renderCompareView(data);
    await renderBenchmarkHistory();
    setText("benchmark-summary", "compared");
    setText("status-message", `Compared ${configA.label} vs ${configB.label}`);
  } catch (error) {
    setText("benchmark-summary", "compare error");
    setText("status-message", `Compare error: ${error.message}`);
  }
}

function renderCompareView(data) {
  const container = $("compare-results");
  if (!container) return;

  const configA = data.config_a || data.baseline || { label: "Config A" };
  const configB = data.config_b || data.target || { label: "Config B" };
  const resultA = data.run_a?.result || data.baseline?.result || {};
  const resultB = data.run_b?.result || data.target?.result || {};
  const diffs = data.diffs || {};
  const taskDiffs = data.task_diffs || [];

  let html = `<div class="compare-header">
    <div class="compare-label baseline-label">${escHtml(configA.label)}</div>
    <div class="compare-label target-label">${escHtml(configB.label)}</div>
  </div>`;

  const metrics = [
    { key: "tok_s_avg", label: "Tok/s", unit: " tok/s", fmt: (v) => formatNumber(v, 2) },
    { key: "latency_p50_seconds", label: "TTFT (ms)", unit: " ms", fmt: (v) => v !== null && v !== undefined ? (v * 1000).toFixed(0) : "--", scale: 1000 },
    { key: "latency_p95_seconds", label: "p95 (ms)", unit: " ms", fmt: (v) => v !== null && v !== undefined ? (v * 1000).toFixed(0) : "--", scale: 1000 },
    { key: "pass_rate", label: "Pass rate", unit: "%", fmt: (v) => formatPercent(v) },
    { key: "duration_seconds", label: "Duration", unit: "s", fmt: (v) => v !== null && v !== undefined ? `${formatNumber(v, 1)}s` : "--" },
    { key: "output_tokens", label: "Output tokens", unit: "", fmt: (v) => v !== null && v !== undefined ? Number(v).toLocaleString() : "--" },
  ];

  html += `<table class="compare-table">
    <thead><tr><th>Metric</th><th>${escHtml(configA.label)}</th><th>${escHtml(configB.label)}</th><th>Δ</th></tr></thead>
    <tbody>`;
  for (const m of metrics) {
    const d = diffs[m.key];
    const valueA = d?.a ?? d?.baseline ?? resultA[m.key];
    const valueB = d?.b ?? d?.target ?? resultB[m.key];
    const deltaHtml = formatDelta(d, m);
    html += `<tr><td>${escHtml(m.label)}</td><td class="val-baseline">${m.fmt(valueA)}</td><td class="val-target">${m.fmt(valueB)}</td><td class="val-delta">${deltaHtml}</td></tr>`;
  }
  html += `</tbody></table>`;

  if (taskDiffs.length > 0) {
    html += `<h4 class="compare-subhead">Per-task breakdown</h4>`;
    html += `<table class="compare-table compare-task-table">
      <thead><tr>
        <th>Task</th>
        <th>${escHtml(configA.label)} Score</th>
        <th>${escHtml(configB.label)} Score</th>
        <th>Δ Score</th>
        <th>${escHtml(configA.label)} tok/s</th>
        <th>${escHtml(configB.label)} tok/s</th>
        <th>Δ tok/s</th>
      </tr></thead>
      <tbody>`;
    for (const td of taskDiffs) {
      const title = escHtml(td.title || td.task_id);
      const passA = td.passed?.a ?? td.passed?.baseline;
      const passB = td.passed?.b ?? td.passed?.target;
      const scoreA = td.score?.a !== undefined && td.score?.a !== null ? (td.score.a * 100).toFixed(0) + "%" : "--";
      const scoreB = td.score?.b !== undefined && td.score?.b !== null ? (td.score.b * 100).toFixed(0) + "%" : "--";
      const tokA = td.tok_s?.a !== undefined && td.tok_s?.a !== null ? formatNumber(td.tok_s.a, 1) : "--";
      const tokB = td.tok_s?.b !== undefined && td.tok_s?.b !== null ? formatNumber(td.tok_s.b, 1) : "--";

      const scoreDeltaHtml = formatDelta(td.score, { scale: 100, unit: "%", digits: 1 });
      const tokDeltaHtml = formatDelta(td.tok_s, { unit: "", digits: 1 });
      const statusA = passA !== undefined ? (passA ? "✅" : "❌") : "—";
      const statusB = passB !== undefined ? (passB ? "✅" : "❌") : "—";
      html += `<tr>
        <td class="task-title">${statusA} ${statusB} ${title}</td>
        <td class="val-baseline">${scoreA}</td>
        <td class="val-target">${scoreB}</td>
        <td class="val-delta">${scoreDeltaHtml}</td>
        <td class="val-baseline">${tokA}</td>
        <td class="val-target">${tokB}</td>
        <td class="val-delta">${tokDeltaHtml}</td>
      </tr>`;
    }
    html += `</tbody></table>`;
  }

  html += `<details class="compare-raw">
    <summary>Raw comparison data</summary>
    <pre class="json-viewer">${syntaxHighlight(JSON.stringify(data, null, 2))}</pre>
  </details>`;

  container.innerHTML = html;
}

function formatDelta(diff, metric = {}) {
  if (!diff || diff.delta === undefined || diff.delta === null) return "--";
  const scale = metric.scale || 1;
  const digits = metric.digits ?? (Math.abs(diff.delta * scale) < 10 ? 2 : 1);
  const delta = diff.delta * scale;
  const sign = delta > 0 ? "+" : "";
  const improved = diff.improved;
  const cls = improved === true ? "delta-good" : improved === false ? "delta-bad" : "delta-flat";
  const mark = improved === true ? "✅" : improved === false ? "❌" : "—";
  return `<span class="${cls}">${sign}${formatNumber(delta, digits)}${metric.unit || ""} ${mark}</span>`;
}

function escHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
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

async function rollbackUpdate() {
  setText("update-result", "Rolling back...");
  try {
    const response = await fetch("/api/update/rollback", { method: "POST" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (data.ok) {
      const name = data.backup_path ? data.backup_path.split("/").pop() : "latest backup";
      setText("update-result", `Rolled back from ${name}. Restart DS4 to apply.`);
    } else {
      setText("update-result", data.error || "Rollback failed.");
    }
  } catch (error) {
    setText("update-result", `Rollback error: ${error.message}`);
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

// ── Model List & Switch ───────────────────────────────────

async function refreshModelList() {
  try {
    const data = await fetchJson("/api/models");
    const select = $("model-select");
    if (!select) return;
    state.models = data.models || [];
    select.replaceChildren();
    for (const m of state.models) {
      const opt = document.createElement("option");
      opt.value = m.path;
      opt.textContent = `${m.filename} (${m.size_gb} GB)`;
      select.append(opt);
    }
    // Show current model in placeholder
    const currentPath = data.current_model || "";
    const currentName = currentPath.split("/").pop() || "--";
    setText("model-summary", currentName);
    // Show per-model averages for all known models
    if (data.averages) {
      for (const [modelName, stats] of Object.entries(data.averages)) {
        if (stats.count > 0 && modelName === currentName) {
          // Already rendered in renderStatus; update summary
          setText("model-summary", `${currentName}: ${stats.total_calls} calls`);
        }
      }
    }
    buildCompareProfiles();
  } catch (error) {
    console.warn("Model list refresh error:", error.message);
  }
}

async function switchModel() {
  const select = $("model-select");
  if (!select || !select.value) return;
  const path = select.value;
  setText("model-summary", `Switching to ${path.split("/").pop()}...`);
  try {
    const result = await fetch("/api/models/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_path: path }),
    });
    if (!result.ok) throw new Error(`HTTP ${result.status}`);
    const data = await result.json();
    if (data.ok) {
      setText("status-message", `Switched to ${path.split("/").pop()} — DS4 restarting.`);
      setText("model-summary", `restarting: ${path.split("/").pop()}`);
    } else {
      setText("status-message", `Switch failed: ${data.result?.error || "unknown"}`);
      setText("model-summary", "switch failed");
    }
  } catch (error) {
    setText("status-message", `Model switch error: ${error.message}`);
    setText("model-summary", "error");
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
  $("config-apply-btn")?.addEventListener("click", () => {
    applyConfig().catch((error) => setText("status-message", error.message));
  });
  $("restart-ds4-btn")?.addEventListener("click", () => {
    restartDS4().catch((error) => setText("status-message", error.message));
  });
  $("run-benchmark")?.addEventListener("click", () => {
    runBenchmark().catch((error) => setText("status-message", error.message));
  });
  $("compare-benchmarks")?.addEventListener("click", () => {
    compareBenchmarks().catch((error) => setText("status-message", error.message));
  });
  $("update-check")?.addEventListener("click", () => {
    checkUpdate().catch((error) => setText("status-message", error.message));
  });
  $("update-rollback")?.addEventListener("click", () => {
    rollbackUpdate().catch((error) => setText("status-message", error.message));
  });
  $("switch-model-btn")?.addEventListener("click", () => {
    switchModel().catch((error) => setText("status-message", error.message));
  });

  // Initial loads
  await Promise.all([
    refreshConfig().catch((error) => setText("status-message", error.message)),
    refreshBenchmarks().catch((error) => console.warn("benchmarks:", error.message)),
    renderBenchmarkHistory().catch((error) => console.warn("history:", error.message)),
    refreshMCP().catch((error) => console.warn("mcp:", error.message)),
    refreshModelList().catch((error) => console.warn("models:", error.message)),
  ]);

  // Start telemetry polling
  await refreshStatus();
  window.setInterval(refreshStatus, POLL_MS);
}

boot();

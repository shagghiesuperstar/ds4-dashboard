const POLL_MS = 2000;

const state = {
  config: null,
  schema: null,
  lastStatus: null,
};

const $ = (id) => document.getElementById(id);

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined || Number.isNaN(Number(bytes))) return "--";
  const value = Number(bytes);
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let size = Math.abs(value);
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
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

function setStateChip(status) {
  const chip = $("status-chip");
  const stateLabel = $("state-label");
  const currentState = status.state || (status.running ? "running" : "stopped");
  if (chip) chip.dataset.state = currentState;
  if (stateLabel) stateLabel.textContent = currentState.toUpperCase();
}

function renderStatus(status) {
  state.lastStatus = status;
  setStateChip(status);

  const config = status.config || state.config || {};
  const telemetry = status.telemetry || {};
  const kv = status.kv_cache || telemetry.kv_cache || config.kv_disk_cache || {};
  const system = status.system || {};
  const memory = system.memory || {};
  const cpu = system.cpu || {};

  const tokens = telemetry.tok_s ?? telemetry.tokens_per_second ?? status.tok_s;
  setText("tokens-sec", tokens === undefined || tokens === null ? "--" : `${formatNumber(tokens, 2)} tok/s`);
  setText("context-window", (config.context_window || status.context_window || "--").toLocaleString?.() || "--");
  setText("kv-cache", kv.used_bytes ? formatBytes(kv.used_bytes) : formatMiB(kv.budget_mib));
  setText("shader-count", String(config.metal?.shader_count ?? "--"));
  setText("status-message", status.message || telemetry.message || "Telemetry online.");
  setText("process-id", status.pid ? String(status.pid) : "--");
  setText("uptime", formatDuration(status.uptime_seconds ?? telemetry.uptime_seconds));

  const usedPercent = memory.used_percent ?? memory.pressure_percent;
  const freePercent = memory.free_percent;
  const fill = $("memory-fill");
  if (fill && usedPercent !== undefined && usedPercent !== null) {
    fill.style.width = `${Math.min(100, Math.max(0, Number(usedPercent)))}%`;
  }
  setText("memory-used", `Used ${memory.used_bytes ? formatBytes(memory.used_bytes) : formatPercent(usedPercent)}`);
  setText("memory-free", `Free ${memory.free_bytes ? formatBytes(memory.free_bytes) : formatPercent(freePercent)}`);
  setText("memory-pressure", memory.pressure || "--");
  const cpuText =
    cpu.usage_percent !== undefined && cpu.usage_percent !== null
      ? formatPercent(cpu.usage_percent)
      : cpu.load_average
        ? `load ${formatNumber(cpu.load_average[0], 2)}`
        : "--";
  setText("cpu-usage", cpuText);

  const logo = document.querySelector(".dwarfstar-logo");
  if (logo) {
    logo.dataset.state = status.state || "unknown";
    logo.style.setProperty("--kv-distortion", String(kv.fill_percent || 0));
  }
}

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

async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

async function refreshConfig() {
  const [config, schema] = await Promise.all([fetchJson("/api/config"), fetchJson("/api/config-schema")]);
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

async function boot() {
  $("refresh-config")?.addEventListener("click", () => {
    refreshConfig().catch((error) => setText("status-message", error.message));
  });
  $("config-save-btn")?.addEventListener("click", () => {
    saveConfig().catch((error) => setText("status-message", error.message));
  });
  await refreshConfig().catch((error) => setText("status-message", error.message));
  await refreshStatus();
  window.setInterval(refreshStatus, POLL_MS);
}

boot();

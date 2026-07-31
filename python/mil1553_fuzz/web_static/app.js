"use strict";

const views = {
  campaign: { title: "测试编排", eyebrow: "FUZZ CAMPAIGN" },
  board: { title: "板卡与目标", eyebrow: "BOARD ADAPTER" },
  logs: { title: "运行日志", eyebrow: "CAMPAIGN OUTPUT" },
};

const state = {
  lastSequence: 0,
  visibleLogs: 0,
  running: false,
  pollTimer: null,
  toastTimer: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function switchView(name) {
  if (!views[name]) return;
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === name));
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${name}`));
  $("#viewTitle").textContent = views[name].title;
  $("#viewEyebrow").textContent = views[name].eyebrow;
}

function selectedValues(name) {
  return $$(`input[name="${name}"]:checked`).map((input) => input.value);
}

function parsePositiveInteger(value, fallback = 0) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function updateSummary() {
  const scenarios = selectedValues("scenario").length;
  const strategies = selectedValues("strategy").length;
  const limit = parsePositiveInteger($("#limit").value);
  const repeatEach = parsePositiveInteger($("#repeatEach").value);
  const backend = $('input[name="backend"]:checked').value;
  const bus = $("#bus").value;
  const channel = $("#channel").value || "0";

  $("#scenarioMetric").textContent = scenarios;
  $("#strategyMetric").textContent = strategies;
  $("#caseMetric").textContent = (limit * repeatEach).toLocaleString("zh-CN");
  $("#busMetric").textContent = bus;
  $("#contextLine").textContent = `${backend === "native" ? "真实板卡" : "模拟后端"} · 总线 ${bus} · 通道 ${channel}`;
  $("#dllPath").disabled = backend !== "native" || state.running;
}

function collectConfig() {
  return {
    scenarios: selectedValues("scenario"),
    strategies: selectedValues("strategy"),
    backend: $('input[name="backend"]:checked').value,
    dll_path: $("#dllPath").value,
    card_index: $("#cardIndex").value,
    channel: $("#channel").value,
    bus: $("#bus").value,
    rt_targets: $("#rtTargets").value,
    subaddresses: $("#subaddresses").value,
    word_counts: $("#wordCounts").value,
    rt2_source: $("#rt2Source").value,
    rt3_destination: $("#rt3Destination").value,
    limit: $("#limit").value,
    repeat_each: $("#repeatEach").value,
    interval_ms: $("#intervalMs").value,
    timeout_ms: $("#timeoutMs").value,
    seed: $("#seed").value,
    out_path: $("#outPath").value,
    no_reset: $("#noReset").checked,
    dry_run: $("#dryRun").checked,
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败：${response.status}`);
  return data;
}

async function startCampaign() {
  setButtonsBusy(true);
  try {
    const result = await api("/api/start", {
      method: "POST",
      body: JSON.stringify(collectConfig()),
    });
    applyServerState(result);
    switchView("logs");
    showToast("测试任务已启动");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    if (!state.running) setButtonsBusy(false);
  }
}

async function stopCampaign(reason = "用户请求停止测试。") {
  if (!state.running) return;
  try {
    const result = await api("/api/stop", {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
    applyServerState(result);
  } catch (error) {
    showToast(error.message, true);
  }
}

function setButtonsBusy(running) {
  state.running = running;
  $("#startButton").disabled = running;
  $("#dockStartButton").disabled = running;
  $("#stopButton").disabled = !running;
  $("#dockStopButton").disabled = !running;
  $$("input, select").forEach((control) => {
    if (control.id !== "dllPath") control.disabled = running;
  });
  updateSummary();
}

function applyServerState(serverState) {
  const running = Boolean(serverState.running);
  setButtonsBusy(running);

  const status = serverState.status || "idle";
  const text = serverState.status_text || "就绪";
  const detail = serverState.status_detail || "等待测试任务";
  const current = Number(serverState.current || 0);
  const total = Number(serverState.total || 0);
  const percent = total > 0 ? Math.min(100, (current / total) * 100) : 0;

  $("#statusText").textContent = text;
  $("#sidebarStatus").textContent = text;
  $("#dockStatus").textContent = text;
  $("#largeStatusText").textContent = text;
  $("#sidebarDetail").textContent = detail;
  $("#dockDetail").textContent = detail;
  $("#largeStatusDetail").textContent = detail;
  $("#progressText").textContent = `${current.toLocaleString("zh-CN")} / ${total.toLocaleString("zh-CN")}`;
  $("#progressBar").style.width = `${percent}%`;
  $("#dockProgress").style.width = `${percent}%`;

  const statusPill = $("#statusPill");
  statusPill.className = `status-pill ${status}`;
  [$("#sidebarDot"), $("#dockDot"), $("#largeStatusDot")].forEach((dot) => {
    dot.dataset.status = status;
    dot.style.background = statusColor(status);
  });

  appendLogs(serverState.logs || []);
}

function statusColor(status) {
  if (status === "error" || status === "stopped") return "#ef765f";
  if (status === "running" || status === "stopping") return "#dfa52d";
  return "#168a7a";
}

function appendLogs(logs) {
  if (!logs.length) return;
  const consoleNode = $("#console");
  $("#emptyLog")?.remove();
  const fragment = document.createDocumentFragment();
  logs.forEach((entry) => {
    if (entry.sequence <= state.lastSequence) return;
    const line = document.createElement("div");
    line.className = `log-line ${entry.level}`;

    const time = document.createElement("span");
    time.className = "log-time";
    time.textContent = entry.time;

    const level = document.createElement("span");
    level.className = "log-level";
    level.textContent = levelLabel(entry.level);

    const message = document.createElement("span");
    message.className = "log-message";
    message.textContent = entry.message;

    line.append(time, level, message);
    fragment.append(line);
    state.lastSequence = Math.max(state.lastSequence, entry.sequence);
    state.visibleLogs += 1;
  });
  consoleNode.append(fragment);
  while (consoleNode.children.length > 1000) consoleNode.firstElementChild.remove();
  consoleNode.scrollTop = consoleNode.scrollHeight;
  $("#logCount").textContent = state.visibleLogs.toLocaleString("zh-CN");
}

function levelLabel(level) {
  return {
    info: "INFO",
    case: "CASE",
    success: "DONE",
    warning: "WARN",
    error: "ERROR",
  }[level] || "LOG";
}

function clearVisibleLogs() {
  $("#console").replaceChildren();
  const empty = document.createElement("div");
  empty.className = "empty-log";
  empty.id = "emptyLog";
  empty.textContent = "日志显示已清空";
  $("#console").append(empty);
  state.visibleLogs = 0;
  $("#logCount").textContent = "0";
}

function showToast(message, error = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.className = `toast show${error ? " error" : ""}`;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => {
    toast.className = "toast";
  }, 3200);
}

async function pollState() {
  try {
    const result = await api(`/api/state?after=${state.lastSequence}`);
    applyServerState(result);
  } catch (error) {
    showToast("本机控制服务连接中断", true);
  } finally {
    state.pollTimer = setTimeout(pollState, state.running ? 350 : 1000);
  }
}

function bindEvents() {
  $$(".nav-item").forEach((item) => item.addEventListener("click", () => switchView(item.dataset.view)));
  $("#startButton").addEventListener("click", startCampaign);
  $("#dockStartButton").addEventListener("click", startCampaign);
  $("#stopButton").addEventListener("click", () => stopCampaign());
  $("#dockStopButton").addEventListener("click", () => stopCampaign());
  $("#clearLogs").addEventListener("click", clearVisibleLogs);
  $("#selectAllScenarios").addEventListener("click", () => {
    $$('input[name="scenario"]').forEach((input) => { input.checked = true; });
    updateSummary();
  });
  $("#clearScenarios").addEventListener("click", () => {
    $$('input[name="scenario"]').forEach((input) => { input.checked = false; });
    updateSummary();
  });
  $$("input, select").forEach((control) => {
    control.addEventListener("input", updateSummary);
    control.addEventListener("change", updateSummary);
  });
  window.addEventListener("pagehide", () => {
    if (state.running) {
      navigator.sendBeacon(
        "/api/stop",
        new Blob([JSON.stringify({ reason: "界面已关闭，自动停止测试。" })], { type: "application/json" }),
      );
    }
  });
}

bindEvents();
updateSummary();
pollState();

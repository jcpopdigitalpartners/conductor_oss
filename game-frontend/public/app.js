const $ = (sel) => document.querySelector(sel);

let workflowId = null;
let pollTimer = null;

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function showError(msg) {
  const el = $("#error");
  el.textContent = msg;
  el.classList.toggle("hidden", !msg);
}

function renderParty(state) {
  const list = $("#party-list");
  list.innerHTML = (state.party || [])
    .map((m) => `<li><strong>${m.name}</strong> · ${m.class} ${m.level}</li>`)
    .join("");

  const stats = [];
  if (state.difficulty) stats.push(`Difficulty: ${state.difficulty}`);
  if (state.partySheet?.partyPower) stats.push(`Power: ${state.partySheet.partyPower}`);
  if (state.partySheet?.partyHp) stats.push(`HP: ${state.partySheet.partyHp}`);
  $("#party-stats").textContent = stats.join(" · ");
}

function renderLog(log) {
  const container = $("#log");
  container.innerHTML = (log || [])
    .map(
      (entry) => `
      <article class="log-entry">
        <h3>${entry.label}</h3>
        <p>${escapeHtml(entry.text)}</p>
      </article>`
    )
    .join("");
  container.scrollTop = container.scrollHeight;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** TERMINATE workflowOutput may pass the full epilogue object, not just text. */
function formatEpilogue(value) {
  if (!value) return null;
  if (typeof value === "string") return value;
  if (typeof value === "object" && typeof value.epilogue === "string") {
    return value.epilogue;
  }
  return null;
}

function phaseLabel(phase) {
  const map = {
    running: "Journey in progress",
    dm_choice: "Awaiting DM",
    victory: "Quest complete",
    defeat: "Quest failed",
    ended: "Ended",
  };
  return map[phase] || phase;
}

function renderState(state) {
  workflowId = state.workflowId;
  showError("");

  $("#status-bar").classList.remove("hidden");
  $("#party-label").textContent = state.partyName || "Party";
  $("#workflow-label").textContent = state.workflowId?.slice(0, 8) + "…";
  $("#phase-label").textContent = phaseLabel(state.phase);

  renderParty(state);
  renderLog(state.log);

  const dmPanel = $("#dm-panel");
  const ending = $("#ending");

  if (state.phase === "dm_choice") {
    dmPanel.classList.remove("hidden");
    ending.classList.add("hidden");
    $("#intel-brief").textContent = state.intel?.briefingForDm || "The party reaches a fork in the dungeon.";
    const report = state.intel?.report || [];
    $("#intel-report").innerHTML = report.map((r) => `<li>${escapeHtml(r)}</li>`).join("");
    document.querySelectorAll(".choices button").forEach((b) => (b.disabled = false));
  } else {
    dmPanel.classList.add("hidden");
  }

  if (state.phase === "victory" || state.phase === "defeat") {
    ending.classList.remove("hidden");
    ending.classList.toggle("victory", state.phase === "victory");
    ending.classList.toggle("defeat", state.phase === "defeat");
    $("#ending-title").textContent =
      state.phase === "victory" ? "Victory" : "Defeat";
    $("#ending-text").textContent =
      formatEpilogue(state.epilogue) ||
      state.reason ||
      "The quest has concluded.";
    const lootEl = $("#ending-loot");
    if (state.loot) {
      lootEl.classList.remove("hidden");
      lootEl.textContent = JSON.stringify(state.loot, null, 2);
    } else {
      lootEl.classList.add("hidden");
    }
    stopPoll();
  }

  $("#btn-start").classList.toggle("hidden", !!workflowId);
  $("#btn-refresh").classList.toggle("hidden", !workflowId || state.phase !== "running");
  $("#btn-new").classList.toggle("hidden", !workflowId);
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function startPoll() {
  stopPoll();
  pollTimer = setInterval(async () => {
    if (!workflowId) return;
    try {
      const state = await api(`/api/quest/${workflowId}`);
      renderState(state);
      if (state.phase !== "running") stopPoll();
    } catch (err) {
      showError(err.message);
      stopPoll();
    }
  }, 1500);
}

async function checkHealth() {
  const footer = $("footer");
  try {
    const h = await api("/api/health");
    footer.textContent = `Conductor CLI ready (${h.conductorCmd})`;
    footer.className = "ok";
  } catch (err) {
    footer.textContent = `Conductor CLI unavailable: ${err.message}`;
    footer.className = "err";
  }
}

$("#btn-start").addEventListener("click", async () => {
  $("#btn-start").disabled = true;
  showError("");
  try {
    const state = await api("/api/quest/start", { method: "POST", body: "{}" });
    renderState(state);
    if (state.phase === "running") startPoll();
  } catch (err) {
    showError(err.message);
  } finally {
    $("#btn-start").disabled = false;
  }
});

$("#btn-refresh").addEventListener("click", async () => {
  if (!workflowId) return;
  try {
    renderState(await api(`/api/quest/${workflowId}`));
  } catch (err) {
    showError(err.message);
  }
});

$("#btn-new").addEventListener("click", () => {
  workflowId = null;
  stopPoll();
  $("#log").innerHTML = "";
  $("#dm-panel").classList.add("hidden");
  $("#ending").classList.add("hidden");
  $("#status-bar").classList.add("hidden");
  $("#btn-start").classList.remove("hidden");
  $("#btn-refresh").classList.add("hidden");
  $("#btn-new").classList.add("hidden");
  showError("");
});

document.querySelectorAll(".choices button").forEach((btn) => {
  btn.addEventListener("click", async () => {
    if (!workflowId) return;
    const approach = btn.dataset.approach;
    const dmNotes = $("#dm-notes").value.trim();
    document.querySelectorAll(".choices button").forEach((b) => (b.disabled = true));
    showError("");
    try {
      const state = await api(`/api/quest/${workflowId}/choose`, {
        method: "POST",
        body: JSON.stringify({ approach, dmNotes }),
      });
      renderState(state);
    } catch (err) {
      showError(err.message);
      document.querySelectorAll(".choices button").forEach((b) => (b.disabled = false));
    }
  });
});

checkHealth();

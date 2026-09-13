/**
 * Jal Rakshak Pipe Node — Diagnostic WebUI (app.js)
 * Uses official Arduino App Lab WebUI brick client (libs/arduino.js)
 */

"use strict";

const ui = new WebUI();

// ── DOM helper ─────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

// ── Payload Unpacking Helper ───────────────────────────────────────────────
function extractData(raw) {
  if (!raw) return {};
  let d = raw;
  if (typeof d === "string") {
    try { d = JSON.parse(d); } catch (e) { return {}; }
  }
  if (d && typeof d === "object" && d.message) {
    if (typeof d.message === "string") {
      try { d = JSON.parse(d.message); } catch (e) { d = d.message; }
    } else {
      d = d.message;
    }
  }
  return d || {};
}

function fmt(v, dec = 1) {
  return (v !== null && v !== undefined && !isNaN(v)) ? Number(v).toFixed(dec) : "—";
}

function fmtTs(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString();
  } catch (e) {
    return iso;
  }
}

// ── Connection Status ──────────────────────────────────────────────────────
ui.on_connect(() => {
  const dot = $("conn-status");
  if (dot) {
    dot.className = "conn-dot conn-ok";
    dot.title = "Connected to Pipe Node MPU";
  }
  // Request full current state immediately upon connecting
  ui.send_message("request_state", {});
});

ui.on_disconnect(() => {
  const dot = $("conn-status");
  if (dot) {
    dot.className = "conn-dot conn-off";
    dot.title = "Disconnected from Pipe Node";
  }
});

// ── State Update Handler ───────────────────────────────────────────────────
ui.on_message("state_update", (raw) => {
  const payload = extractData(raw);
  if (payload.sensors) updateSensors(payload.sensors);
  if (payload.acoustic) updateAudio(payload.acoustic);
  if (payload.system) updateSystem(payload.system);
});

// ── Audio Update Handler (Edge AI Stream) ──────────────────────────────────
ui.on_message("audio_update", (raw) => {
  const payload = extractData(raw);
  updateAudio(payload);
});

// ── Render Functions ───────────────────────────────────────────────────────
function updateAudio(a) {
  if (!a) return;

  let leakPct = 0;
  let noisePct = 0;

  // Extract from classifications map if available
  if (a.classifications && typeof a.classifications === "object") {
    for (const [key, val] of Object.entries(a.classifications)) {
      const k = key.toLowerCase();
      const pct = Math.round(Number(val) * 100);
      if (k.includes("leak")) {
        leakPct = pct;
      } else {
        noisePct = pct;
      }
    }
  } else if (a.label && a.confidence !== undefined) {
    const conf = Math.round(Number(a.confidence) * 100);
    if (a.label.toLowerCase().includes("leak")) {
      leakPct = conf;
      noisePct = Math.max(0, 100 - conf);
    } else {
      noisePct = conf;
      leakPct = Math.max(0, 100 - conf);
    }
  }

  // Update bar tracks
  if ($("bar-leak")) $("bar-leak").style.width = leakPct + "%";
  if ($("bar-noise")) $("bar-noise").style.width = noisePct + "%";
  if ($("pct-leak")) $("pct-leak").textContent = leakPct + "%";
  if ($("pct-noise")) $("pct-noise").textContent = noisePct + "%";
  if ($("consec-count")) $("consec-count").textContent = a.consecutive_count || 0;
  if ($("ai-timestamp")) $("ai-timestamp").textContent = fmtTs(a.timestamp);

  const lbl = $("ai-label");
  if (lbl) {
    if (a.leak_confirmed) {
      lbl.textContent = "🚨 LEAK CONFIRMED";
      lbl.className = "ai-label danger";
      showEmergency("Acoustic leak confirmed! Emergency LoRa packet transmitted.");
    } else if (a.label && a.label.toLowerCase().includes("leak") && leakPct >= 75) {
      lbl.textContent = `⚠ LEAK DETECTED (${leakPct}%)`;
      lbl.className = "ai-label danger";
    } else if (noisePct > 0 || leakPct > 0) {
      lbl.textContent = `✔ NORMAL / CLEAR (${noisePct}%)`;
      lbl.className = "ai-label safe";
      hideEmergency();
    }
  }
}

function updateSensors(s) {
  if (!s) return;

  if ($("val-ph")) $("val-ph").textContent = fmt(s.ph, 2);
  if ($("val-tds")) $("val-tds").textContent = fmt(s.tds, 0) + " ppm";
  if ($("val-turb")) $("val-turb").textContent = fmt(s.turbidity, 1) + " NTU";
  if ($("val-temp")) $("val-temp").textContent = fmt(s.temperature, 1) + "°C";

  if ($("inf-nodeid")) $("inf-nodeid").textContent = `Pipe Node ${s.nodeId || 1}`;
  if ($("inf-gps")) $("inf-gps").textContent = `${fmt(s.latitude, 4)}°N, ${fmt(s.longitude, 4)}°E`;
  if ($("inf-ts")) $("inf-ts").textContent = fmtTs(s.timestamp);

  // Status flags
  updateFlag($("flag-flow"), s.waterPresence, "⬤ Flow Active", "⬤ No Flow");
  updateFlag($("flag-leak"), s.leakAlert, "⬤ LEAK ALERT", "⬤ Leak Clear", true);
  updateFlag($("flag-emg"), s.emergencyFlag, "⬤ EMERGENCY", "⬤ Quality Normal", true);

  // Status badge in header
  const sb = $("status-badge");
  if (sb) {
    sb.textContent = s.status || "NORMAL";
    sb.className = "badge " + statusClass(s.status);
  }

  if (s.emergencyFlag && !s.leakAlert) {
    showEmergency(`Contamination alert: pH=${fmt(s.ph, 2)}, Turb=${fmt(s.turbidity, 1)} NTU`);
  } else if (!s.emergencyFlag && !s.leakAlert) {
    hideEmergency();
  }
}

function updateSystem(sys) {
  if (!sys) return;

  if ($("inf-lora")) $("inf-lora").textContent = sys.lora_active ? "✔ Active (433 MHz)" : "Waiting for Tx…";
  if ($("inf-ai")) $("inf-ai").textContent = sys.ai_running ? "✔ Listening (USB Mic)" : "Mic Not Detected";

  const loraBadge = $("lora-badge");
  if (loraBadge) {
    loraBadge.className = "badge " + (sys.lora_active ? "badge-info" : "badge-offline");
  }

  const lbl = $("ai-label");
  if (lbl && sys.ai_running === false && !lbl.textContent.includes("LEAK")) {
    lbl.textContent = "MIC NOT DETECTED";
    lbl.className = "ai-label";
  } else if (lbl && sys.ai_running === true && lbl.textContent === "MIC NOT DETECTED") {
    lbl.textContent = "LISTENING…";
    lbl.className = "ai-label safe";
  }
}

function updateFlag(el, active, onText, offText, isDanger = false) {
  if (!el) return;
  if (active) {
    el.textContent = onText;
    el.className = "flag " + (isDanger ? "flag-on-danger" : "flag-on-safe");
  } else {
    el.textContent = offText;
    el.className = "flag flag-off";
  }
}

function statusClass(s) {
  if (!s) return "badge-offline";
  const m = {
    NORMAL: "badge-normal",
    WARNING: "badge-warning",
    LEAK_ALERT: "badge-danger",
    EMERGENCY: "badge-danger",
    CONTAMINATION: "badge-danger",
    STARTING: "badge-offline",
    OFFLINE: "badge-offline",
  };
  return m[s] || "badge-offline";
}

// ── Emergency Banner ───────────────────────────────────────────────────────
function showEmergency(msg) {
  const b = $("emergency-banner");
  if (b) {
    b.classList.remove("hidden");
    const t = $("emergency-text");
    if (t) t.textContent = "🚨 " + msg;
  }
}

function hideEmergency() {
  const b = $("emergency-banner");
  if (b) b.classList.add("hidden");
}

// ── Button Controls ────────────────────────────────────────────────────────
const btnLora = $("btn-force-lora");
if (btnLora) {
  btnLora.addEventListener("click", () => {
    ui.send_message("force_lora", {});
    btnLora.textContent = "⚡ Sending…";
    setTimeout(() => { btnLora.textContent = "⚡ Force LoRa Tx"; }, 2000);
  });
}

const btnRefresh = $("btn-refresh");
if (btnRefresh) {
  btnRefresh.addEventListener("click", () => {
    ui.send_message("request_state", {});
  });
}
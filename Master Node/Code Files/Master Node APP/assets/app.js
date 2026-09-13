/* ===================================================================
   Jal Rakshak : Decentralized Water Quality Monitoring System
   Master Node Frontend — Real-Time LoRa Telemetry, Chart, Indore Map & Diagnostics
   =================================================================== */

"use strict";

const ui = new WebUI();

// ── Application State Store ─────────────────────────────────────────
const state = {
  selectedNodeId: 1,
  nodes: {
    1: { nodeId: 1, name: "Pipe Node 1 - Central Indore", latitude: 22.7196, longitude: 75.8577, ph: 0.0, tds: 0.0, turbidity: 0.0, temperature: 0.0, waterPresence: false, leakAlert: false, emergencyFlag: false, status: "OFFLINE", emergencyReason: null, timestamp: null, online: false, hasData: false },
    2: { nodeId: 2, name: "Pipe Node 2 - Vijay Nagar", latitude: 22.7533, longitude: 75.8937, ph: 0.0, tds: 0.0, turbidity: 0.0, temperature: 0.0, waterPresence: false, leakAlert: false, emergencyFlag: false, status: "OFFLINE", emergencyReason: null, timestamp: null, online: false, hasData: false },
    3: { nodeId: 3, name: "Pipe Node 3 - Bhawarkua", latitude: 22.6926, longitude: 75.8676, ph: 0.0, tds: 0.0, turbidity: 0.0, temperature: 0.0, waterPresence: false, leakAlert: false, emergencyFlag: false, status: "OFFLINE", emergencyReason: null, timestamp: null, online: false, hasData: false },
    4: { nodeId: 4, name: "Pipe Node 4 - Palasia", latitude: 22.7244, longitude: 75.8839, ph: 0.0, tds: 0.0, turbidity: 0.0, temperature: 0.0, waterPresence: false, leakAlert: false, emergencyFlag: false, status: "OFFLINE", emergencyReason: null, timestamp: null, online: false, hasData: false }
  },
  gas: { nh3_ppm: 0.0, h2s_ppm: 0.0, timestamp: null },
  vision: { label: "waiting", confidence: 0.0, classifications: {}, timestamp: null },
  verdict: { isContaminated: false, status: "WATER SAFE & CLEAR", badgeClass: "b-safe", color: "green", details: "Diagnostics initialized.", timestamp: null },
  diagnostics: { camera_active: true, gas_active: false },
  emergencies: [],
  system: { wifi: true, firebase: false, lora_active: false, last_packet_time: null }
};

let map = null;
const mapMarkers = {};

// ── Initialize Indore Map (Leaflet) ─────────────────────────────────
function initIndoreMap() {
  const mapElement = document.getElementById("indore-map");
  if (!mapElement || map) return;

  map = L.map("indore-map", {
    center: [22.7196, 75.8577],
    zoom: 12,
    zoomControl: true
  });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  }).addTo(map);

  const indoreIcon = L.divIcon({
    className: "custom-city-marker",
    html: '<span style="background:#ff1744;width:12px;height:12px;display:inline-block;border-radius:50%;border:2px solid #fff;"></span> <strong style="color:#d50000;font-size:12px;background:rgba(255,255,255,0.85);padding:2px 4px;border-radius:4px;">INDORE</strong>',
    iconSize: [80, 20],
    iconAnchor: [6, 6]
  });
  L.marker([22.7196, 75.8577], { icon: indoreIcon }).addTo(map);

  renderMapMarkers();
}

function renderMapMarkers() {
  if (!map) return;

  for (let i = 1; i <= 4; i++) {
    const node = state.nodes[i];
    const isEmergency = node.emergencyFlag || node.leakAlert;
    const isWarning = node.status === "WARNING";
    const isOnline = node.online && node.hasData;
    const markerColor = isEmergency ? "#ff1744" : isWarning ? "#ffab00" : isOnline ? "#00e676" : "#607d8b";

    const customIcon = L.divIcon({
      className: `node-marker-icon marker-node-${i}`,
      html: `<div style="background:${markerColor};width:16px;height:16px;border-radius:50%;border:3px solid #fff;box-shadow:0 0 10px ${markerColor};"></div>`,
      iconSize: [16, 16],
      iconAnchor: [8, 8]
    });

    const popupContent = `
      <div style="font-family:sans-serif;color:#111;font-size:12px;line-height:1.4;">
        <strong style="font-size:14px;color:#0055b3;">${node.name}</strong><br>
        <strong>Status:</strong> <span style="color:${markerColor};font-weight:bold;">${node.status}</span><br>
        ${node.hasData ? `
          <strong>pH:</strong> ${node.ph.toFixed(2)} | <strong>TDS:</strong> ${node.tds.toFixed(0)} ppm<br>
          <strong>Turbidity:</strong> ${node.turbidity.toFixed(1)} NTU | <strong>Temp:</strong> ${node.temperature.toFixed(1)} °C<br>
          <strong>Leak:</strong> ${node.leakAlert ? '🚨 DETECTED' : 'CLEAR'} | <strong>Water:</strong> ${node.waterPresence ? 'YES' : 'NO'}<br>
        ` : `<em>Awaiting LoRa transmission...</em><br>`}
        <button onclick="selectNode(${i})" style="margin-top:6px;background:#0084ff;color:#fff;border:none;padding:4px 8px;border-radius:4px;cursor:pointer;font-size:11px;">View Telemetry</button>
      </div>
    `;

    if (mapMarkers[i]) {
      mapMarkers[i].setLatLng([node.latitude, node.longitude]);
      mapMarkers[i].setIcon(customIcon);
      mapMarkers[i].setPopupContent(popupContent);
    } else {
      const marker = L.marker([node.latitude, node.longitude], { icon: customIcon }).addTo(map);
      marker.bindPopup(popupContent);
      mapMarkers[i] = marker;
    }
  }
}

// ── Node Selection ──────────────────────────────────────────────────
function selectNode(nodeId) {
  state.selectedNodeId = nodeId;

  for (let i = 1; i <= 4; i++) {
    const btn = document.getElementById(`node-btn-${i}`);
    if (btn) btn.classList.toggle("active", i === nodeId);
  }

  const titleEl = document.getElementById("telemetry-node-title");
  if (titleEl) titleEl.textContent = `Live Telemetry - Pipe Node ${nodeId}`;

  renderTelemetryChart();
  updateNodeStats();

  if (map && mapMarkers[nodeId]) {
    mapMarkers[nodeId].openPopup();
    map.panTo([state.nodes[nodeId].latitude, state.nodes[nodeId].longitude]);
  }

  ui.send_message("select_node", nodeId);
}

// ── Render Bar Chart ────────────────────────────────────────────────
function renderTelemetryChart() {
  const chartArea = document.getElementById("telemetry-chart");
  const timeAxis = document.getElementById("chart-x-time");
  const headerTime = document.getElementById("telemetry-timestamp");
  if (!chartArea) return;

  const node = state.nodes[state.selectedNodeId];
  if (!node) return;

  if (!node.hasData) {
    chartArea.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-style:italic;font-size:0.9rem;">
        📡 Awaiting LoRa data for Pipe Node ${node.nodeId}...
      </div>
    `;
    if (timeAxis) timeAxis.textContent = "--:--:--";
    if (headerTime) headerTime.textContent = "Status: Offline";
    return;
  }

  const currentTime = node.timestamp ? formatTimeOnly(node.timestamp) : "--:--:--";
  if (timeAxis) timeAxis.textContent = currentTime;
  if (headerTime) headerTime.textContent = `Time: ${currentTime} (${node.status})`;

  const maxH = 160;

  const hPH = Math.min(Math.max((node.ph / 14.0) * (maxH * 0.25), 8), maxH);
  const hTDS = Math.min(Math.max((node.tds / 200.0) * maxH, 12), maxH);
  const hTurb = Math.min(Math.max((node.turbidity / 100.0) * (maxH * 0.3), 6), maxH);
  const hTemp = Math.min(Math.max((node.temperature / 50.0) * (maxH * 0.4), 12), maxH);

  chartArea.innerHTML = `
    <div class="chart-bar-group">
      <div class="c-bar ph-bar" style="height: ${hPH}px;">
        <span class="bar-tooltip">pH: ${node.ph.toFixed(2)}</span>
      </div>
      <div class="c-bar tds-bar" style="height: ${hTDS}px;">
        <span class="bar-tooltip">TDS: ${node.tds.toFixed(0)} ppm</span>
      </div>
      <div class="c-bar turb-bar" style="height: ${hTurb}px;">
        <span class="bar-tooltip">Turb: ${node.turbidity.toFixed(1)}</span>
      </div>
      <div class="c-bar temp-bar" style="height: ${hTemp}px;">
        <span class="bar-tooltip">Temp: ${node.temperature.toFixed(1)}°C</span>
      </div>
    </div>
  `;
}

// ── Update Node Stats Display ───────────────────────────────────────
function updateNodeStats() {
  const node = state.nodes[state.selectedNodeId];
  if (!node) return;

  const phEl = document.getElementById("stat-ph");
  const tdsEl = document.getElementById("stat-tds");
  const turbEl = document.getElementById("stat-turb");
  const tempEl = document.getElementById("stat-temp");
  const waterEl = document.getElementById("stat-water");
  const leakEl = document.getElementById("stat-leak");

  if (node.hasData) {
    if (phEl) phEl.textContent = node.ph.toFixed(2);
    if (tdsEl) tdsEl.innerHTML = `${node.tds.toFixed(0)} <small>ppm</small>`;
    if (turbEl) turbEl.innerHTML = `${node.turbidity.toFixed(1)} <small>NTU</small>`;
    if (tempEl) tempEl.innerHTML = `${node.temperature.toFixed(1)} <small>°C</small>`;
    if (waterEl) waterEl.innerHTML = node.waterPresence ? '<span class="badge b-safe">YES</span>' : '<span class="badge b-danger">NO</span>';
    if (leakEl) leakEl.innerHTML = node.leakAlert ? '<span class="badge b-danger">LEAK DETECTED</span>' : '<span class="badge b-safe">CLEAR</span>';
  } else {
    if (phEl) phEl.textContent = "--";
    if (tdsEl) tdsEl.innerHTML = `-- <small>ppm</small>`;
    if (turbEl) turbEl.innerHTML = `-- <small>NTU</small>`;
    if (tempEl) tempEl.innerHTML = `-- <small>°C</small>`;
    if (waterEl) waterEl.innerHTML = '<span class="badge b-neutral">OFFLINE</span>';
    if (leakEl) leakEl.innerHTML = '<span class="badge b-neutral">OFFLINE</span>';
  }

  // Update left sidebar status dots
  for (let i = 1; i <= 4; i++) {
    const n = state.nodes[i];
    const dot = document.getElementById(`node-dot-${i}`);
    const sub = document.getElementById(`node-sub-${i}`);
    const btn = document.getElementById(`node-btn-${i}`);

    if (dot && n) {
      dot.className = `node-dot ${n.emergencyFlag || n.leakAlert ? 'danger' : n.status === 'WARNING' ? 'warn' : n.hasData ? 'safe' : 'offline'}`;
    }
    if (sub && n) {
      sub.textContent = n.emergencyReason || (n.hasData ? `${n.status} • Live` : `Offline • Waiting LoRa`);
    }
    if (btn && n) {
      btn.classList.toggle("emergency", !!(n.emergencyFlag || n.leakAlert));
    }
  }
}

// ── Emergency Alert Banner ──────────────────────────────────────────
function updateEmergencyBanner() {
  const banner = document.getElementById("emergency-banner");
  const text = document.getElementById("emergency-text");
  if (!banner || !text) return;

  if (state.emergencies && state.emergencies.length > 0) {
    text.textContent = state.emergencies[0];
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

// ── Camera Stream Iframe ────────────────────────────────────────────
// Camera hardware is ALWAYS running (managed by App.run).
// Start/Stop only toggles classification forwarding + iframe visibility.
const currentHostname = window.location.hostname || "localhost";
const baseStreamUrl = `http://${currentHostname}:4912/embed`;

function loadCameraStream() {
  const iframe = document.getElementById("dynamicIframe");
  const placeholder = document.getElementById("videoPlaceholder");
  const statusText = document.getElementById("cam-status-text");
  if (!iframe || !placeholder) return;

  // Camera hardware is always on — just show/hide the iframe
  if (statusText) statusText.textContent = "Connecting to camera stream...";
  placeholder.style.display = "flex";
  iframe.style.display = "none";

  iframe.onload = () => {
    placeholder.style.display = "none";
    iframe.style.display = "block";
    if (statusText) statusText.textContent = "Camera Live";
  };

  iframe.src = `${baseStreamUrl}?t=${Date.now()}`;
}

// ── Diagnostic Controls ─────────────────────────────────────────────
function startCameraTest() {
  state.diagnostics.camera_active = true;
  const btnStart = document.getElementById("btn-cam-start");
  const btnStop = document.getElementById("btn-cam-stop");
  const statusText = document.getElementById("cam-status-text");
  if (btnStart) btnStart.style.opacity = "0.6";
  if (btnStop) btnStop.style.opacity = "1";
  if (statusText) statusText.textContent = "Classification Active";

  // Show iframe (camera hardware is always running)
  const iframe = document.getElementById("dynamicIframe");
  const placeholder = document.getElementById("videoPlaceholder");
  if (iframe && iframe.style.display === "none") {
    loadCameraStream();
  }

  ui.send_message("start_camera_test", {});
}

function stopCameraTest() {
  state.diagnostics.camera_active = false;
  const btnStart = document.getElementById("btn-cam-start");
  const btnStop = document.getElementById("btn-cam-stop");
  const statusText = document.getElementById("cam-status-text");
  if (btnStart) btnStart.style.opacity = "1";
  if (btnStop) btnStop.style.opacity = "0.6";
  if (statusText) statusText.textContent = "Classification Paused (camera still running)";

  // Just hide the iframe, don't tear down the stream
  const iframe = document.getElementById("dynamicIframe");
  const placeholder = document.getElementById("videoPlaceholder");
  if (iframe) iframe.style.display = "none";
  if (placeholder) placeholder.style.display = "flex";

  ui.send_message("stop_camera_test", {});
}

function startGasTest() {
  state.diagnostics.gas_active = true;
  const btnStart = document.getElementById("btn-gas-start");
  const btnStop = document.getElementById("btn-gas-stop");
  if (btnStart) btnStart.style.opacity = "0.6";
  if (btnStop) btnStop.style.opacity = "1";
  ui.send_message("start_gas_test", {});
}

function stopGasTest() {
  state.diagnostics.gas_active = false;
  const btnStart = document.getElementById("btn-gas-start");
  const btnStop = document.getElementById("btn-gas-stop");
  if (btnStart) btnStart.style.opacity = "1";
  if (btnStop) btnStop.style.opacity = "0.6";
  ui.send_message("stop_gas_test", {});
}

// ── Confidence Slider ───────────────────────────────────────────────
const slider = document.getElementById("confidenceSlider");
const confDisplay = document.getElementById("conf-val");
if (slider && confDisplay) {
  slider.addEventListener("input", (e) => {
    const val = parseFloat(e.target.value).toFixed(2);
    confDisplay.textContent = val;
    ui.send_message("override_threshold", val);
  });
}

// ── Verdict & Vision UI ─────────────────────────────────────────────
function updateVerdictUI(verdict) {
  if (!verdict) return;
  const card = document.getElementById("verdict-card");
  const title = document.getElementById("verdict-title");
  const badge = document.getElementById("verdict-badge");
  const details = document.getElementById("verdict-details");

  if (title) title.textContent = verdict.status;
  if (details) details.textContent = verdict.details;
  if (badge) {
    badge.textContent = verdict.isContaminated ? "WATER CONTAMINATED" : "WATER SAFE";
    badge.className = `badge ${verdict.badgeClass}`;
  }
  if (card) {
    card.className = `verdict-card ${verdict.color === 'red' ? 'danger' : verdict.color === 'orange' ? 'warning' : 'safe'}`;
  }
}

function updateVisionUI(vision) {
  if (!vision) return;
  const labelDisplay = document.getElementById("vision-label-display");
  const bar = document.getElementById("vision-confidence-bar");
  const badPct = document.getElementById("vision-bad-pct");
  const goodPct = document.getElementById("vision-good-pct");

  const cls = vision.classifications || {};
  let badVal = cls["bad_water"] || cls["Drain Contaminated water"] || cls["drain_contaminated_water"] || 0;
  let goodVal = cls["good_water"] || cls["Pure Water"] || cls["pure_water"] || 0;

  if (!badVal && !goodVal) {
    for (const [k, v] of Object.entries(cls)) {
      const lower = k.toLowerCase();
      if (lower.includes("drain") || lower.includes("contaminat") || lower.includes("bad")) {
        badVal = v;
      } else if (lower.includes("pure") || lower.includes("good") || lower.includes("clean")) {
        goodVal = v;
      }
    }
  }

  const badScore = Math.round(badVal * 100);
  const goodScore = Math.round(goodVal * 100);
  const isBad = vision.label && (vision.label.toLowerCase().includes("bad") || vision.label.toLowerCase().includes("drain") || vision.label.toLowerCase().includes("contaminat"));

  if (labelDisplay) {
    labelDisplay.textContent = `${vision.label.toUpperCase()} (${(vision.confidence * 100).toFixed(1)}%)`;
    labelDisplay.className = isBad ? "c-danger" : "c-safe";
  }
  if (bar) {
    bar.style.width = `${Math.max(badScore, goodScore)}%`;
    bar.style.backgroundColor = isBad ? "var(--danger)" : "var(--safe)";
  }
  if (badPct) badPct.textContent = `Contaminated: ${badScore}%`;
  if (goodPct) goodPct.textContent = `Pure Water: ${goodScore}%`;
}

function updateGasUI(gas) {
  if (!gas) return;
  const nh3 = document.getElementById("gas-nh3");
  const h2s = document.getElementById("gas-h2s");

  if (nh3) {
    nh3.innerHTML = `${gas.nh3_ppm.toFixed(2)} <small>ppm</small>`;
    nh3.className = `gas-val ${gas.nh3_ppm >= 10.0 ? "c-danger" : gas.nh3_ppm >= 2.0 ? "c-warn" : ""}`;
  }
  if (h2s) {
    h2s.innerHTML = `${gas.h2s_ppm.toFixed(2)} <small>ppm</small>`;
    h2s.className = `gas-val ${gas.h2s_ppm >= 2.0 ? "c-danger" : gas.h2s_ppm >= 0.5 ? "c-warn" : ""}`;
  }
}

function updateSystemUI(sys) {
  if (!sys) return;
  const pillWifi = document.getElementById("pill-wifi");
  const pillFb = document.getElementById("pill-firebase");
  const pillLoRa = document.getElementById("pill-lora");
  const footerInfo = document.getElementById("footer-packet-info");

  if (pillWifi) pillWifi.className = `status-pill ${sys.wifi ? 'safe' : 'danger'}`;
  if (pillFb) pillFb.className = `status-pill ${sys.firebase ? 'safe' : 'neutral'}`;
  if (pillLoRa) pillLoRa.className = `status-pill ${sys.lora_active ? 'safe' : 'neutral'}`;

  if (footerInfo && sys.last_packet_time) {
    footerInfo.textContent = `Last LoRa RX: ${formatTimeOnly(sys.last_packet_time)}`;
  }
}

// ── Helpers ──────────────────────────────────────────────────────────
function formatTimeOnly(isoStr) {
  if (!isoStr) return "--:--:--";
  const d = new Date(isoStr);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

// ── WebUI WebSocket Event Listeners ─────────────────────────────────
ui.on_connect(() => {
  console.log("[Jal Rakshak] Connected to Master Node");
  ui.send_message("request_initial_state", {});
});

ui.on_message("initial_state", (raw) => {
  try {
    const data = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (data.nodes) state.nodes = data.nodes;
    if (data.gas) state.gas = data.gas;
    if (data.vision) state.vision = data.vision;
    if (data.verdict) state.verdict = data.verdict;
    if (data.emergencies) state.emergencies = data.emergencies;
    if (data.system) state.system = data.system;
    if (data.diagnostics) state.diagnostics = data.diagnostics;

    initIndoreMap();
    renderMapMarkers();
    selectNode(state.selectedNodeId);
    updateGasUI(state.gas);
    updateVisionUI(state.vision);
    updateVerdictUI(state.verdict);
    updateSystemUI(state.system);
    updateEmergencyBanner();
    loadCameraStream();
  } catch (err) {
    console.error("Error parsing initial_state:", err);
  }
});

ui.on_message("node_update", (raw) => {
  try {
    const node = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (node && node.nodeId) {
      state.nodes[node.nodeId] = node;
      updateNodeStats();
      renderMapMarkers();
      if (state.selectedNodeId === node.nodeId) {
        renderTelemetryChart();
      }
    }
  } catch (err) {
    console.error("node_update error:", err);
  }
});

ui.on_message("emergency_status", (raw) => {
  try {
    const list = typeof raw === "string" ? JSON.parse(raw) : raw;
    state.emergencies = list || [];
    updateEmergencyBanner();
  } catch (err) {
    console.error("emergency_status error:", err);
  }
});

ui.on_message("vision_update", (raw) => {
  try {
    const data = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (data.vision) { state.vision = data.vision; updateVisionUI(state.vision); }
    if (data.verdict) { state.verdict = data.verdict; updateVerdictUI(state.verdict); }
  } catch (err) {
    console.error("vision_update error:", err);
  }
});

ui.on_message("gas_update", (raw) => {
  try {
    const data = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (data.gas) { state.gas = data.gas; updateGasUI(state.gas); }
    if (data.verdict) { state.verdict = data.verdict; updateVerdictUI(state.verdict); }
  } catch (err) {
    console.error("gas_update error:", err);
  }
});

ui.on_message("system_status", (raw) => {
  try {
    const sys = typeof raw === "string" ? JSON.parse(raw) : raw;
    state.system = sys;
    updateSystemUI(state.system);
  } catch (err) {
    console.error("system_status error:", err);
  }
});

ui.on_message("camera_status", (raw) => {
  try {
    const data = typeof raw === "string" ? JSON.parse(raw) : raw;
    state.diagnostics.camera_active = data.active;
  } catch (err) {}
});

ui.on_message("gas_status", (raw) => {
  try {
    const data = typeof raw === "string" ? JSON.parse(raw) : raw;
    state.diagnostics.gas_active = data.active;
  } catch (err) {}
});

// Initial boot
window.addEventListener("DOMContentLoaded", () => {
  initIndoreMap();
  selectNode(1);
});

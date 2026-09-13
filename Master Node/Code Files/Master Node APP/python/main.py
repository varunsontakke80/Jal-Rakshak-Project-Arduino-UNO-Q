#!/usr/bin/env python3
"""
Jal Rakshak Master Node — Arduino App Lab Brick Application.
Runs on the Qualcomm Dragonwing MPU (Linux) using official Arduino App Bricks:
  - VideoImageClassification Brick (Edge Impulse Vision-AI water classification)
  - WebUI Brick (WebSocket UI hosting on port 7000 from assets/)
  - RouterBridge (MessagePack RPC with STM32 MCU for LoRa, MQ sensors, Buzzer)
  - Firebase Realtime Database cloud telemetry

Camera lifecycle is fully managed by App.run() — never call .start()/.stop()
on the VideoImageClassification brick (matches official Arduino examples).
"""

from arduino.app_utils import *
from arduino.app_bricks.web_ui import WebUI
from arduino.app_bricks.video_imageclassification import VideoImageClassification
from datetime import datetime, UTC
import json
import logging
import threading
import time
import requests

from config import FIREBASE_URL, FIREBASE_AUTH

# ── Logging ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("jal-rakshak-master-node")

# ── Initialize Bricks ───────────────────────────────────────────────────
ui = WebUI()
detection_stream = VideoImageClassification(confidence=0.5, debounce_sec=0.0)

# ── Application State ───────────────────────────────────────────────────
node_data = {
    1: {
        "nodeId": 1, "name": "Pipe Node 1 - Central Indore",
        "latitude": 22.7196, "longitude": 75.8577,
        "ph": 0.0, "tds": 0.0, "turbidity": 0.0, "temperature": 0.0,
        "waterPresence": False, "leakAlert": False, "emergencyFlag": False,
        "status": "OFFLINE", "emergencyReason": None, "timestamp": None,
        "online": False, "hasData": False
    },
    2: {
        "nodeId": 2, "name": "Pipe Node 2 - Vijay Nagar",
        "latitude": 22.7533, "longitude": 75.8937,
        "ph": 0.0, "tds": 0.0, "turbidity": 0.0, "temperature": 0.0,
        "waterPresence": False, "leakAlert": False, "emergencyFlag": False,
        "status": "OFFLINE", "emergencyReason": None, "timestamp": None,
        "online": False, "hasData": False
    },
    3: {
        "nodeId": 3, "name": "Pipe Node 3 - Bhawarkua",
        "latitude": 22.6926, "longitude": 75.8676,
        "ph": 0.0, "tds": 0.0, "turbidity": 0.0, "temperature": 0.0,
        "waterPresence": False, "leakAlert": False, "emergencyFlag": False,
        "status": "OFFLINE", "emergencyReason": None, "timestamp": None,
        "online": False, "hasData": False
    },
    4: {
        "nodeId": 4, "name": "Pipe Node 4 - Palasia",
        "latitude": 22.7244, "longitude": 75.8839,
        "ph": 0.0, "tds": 0.0, "turbidity": 0.0, "temperature": 0.0,
        "waterPresence": False, "leakAlert": False, "emergencyFlag": False,
        "status": "OFFLINE", "emergencyReason": None, "timestamp": None,
        "online": False, "hasData": False
    }
}

diagnostic_state = {
    "camera_active": True,
    "gas_active": False,
    "selected_node": 1
}

latest_gas = {
    "nh3_ppm": 0.0,
    "h2s_ppm": 0.0,
    "timestamp": None
}

latest_vision = {
    "label": "waiting",
    "confidence": 0.0,
    "classifications": {"good_water": 0.0, "bad_water": 0.0},
    "timestamp": None
}

latest_verdict = {
    "isContaminated": False,
    "status": "WATER SAFE & CLEAR",
    "badgeClass": "b-safe",
    "color": "green",
    "details": "Diagnostics initialized. Camera and gas testing ready.",
    "timestamp": None
}

active_emergencies = {}

system_status = {
    "wifi": True,
    "firebase": False,
    "lora_active": False,
    "last_packet_time": None
}

# ── Helper: Compute Combined Water Quality Verdict ──────────────────────
def compute_water_verdict(gas_data, vision_data):
    nh3 = gas_data.get("nh3_ppm", 0.0)
    h2s = gas_data.get("h2s_ppm", 0.0)
    label = vision_data.get("label", "")
    conf = vision_data.get("confidence", 0.0)

    # Support both trained EI model classes ("Drain Contaminated water" / "Pure Water") and standard aliases
    label_lower = label.lower()
    is_bad = any(k in label_lower for k in ["bad", "drain", "contaminat"])
    vision_bad = (is_bad and conf >= 0.65)
    gas_severe = (nh3 >= 10.0 or h2s >= 2.0)
    gas_mild = (nh3 >= 2.0 or h2s >= 0.5)

    if gas_severe:
        return {
            "isContaminated": True, "status": "WATER CONTAMINATED (SEVERE SEWAGE)",
            "badgeClass": "b-danger", "color": "red",
            "details": f"Severe sewage gas: NH3={nh3:.2f}ppm, H2S={h2s:.2f}ppm.",
            "nh3_ppm": round(nh3, 2), "h2s_ppm": round(h2s, 2),
            "vision_label": label, "vision_confidence": round(conf * 100, 1),
            "timestamp": datetime.now(UTC).isoformat()
        }
    elif gas_mild and vision_bad:
        return {
            "isContaminated": True, "status": "WATER CONTAMINATED (CONFIRMED)",
            "badgeClass": "b-danger", "color": "red",
            "details": f"Vision AI + gas sensors both confirm contamination.",
            "nh3_ppm": round(nh3, 2), "h2s_ppm": round(h2s, 2),
            "vision_label": label, "vision_confidence": round(conf * 100, 1),
            "timestamp": datetime.now(UTC).isoformat()
        }
    elif vision_bad:
        return {
            "isContaminated": True, "status": "WATER CONTAMINATED (VISUAL)",
            "badgeClass": "b-danger", "color": "red",
            "details": f"Visual classification: BAD ({conf*100:.1f}%).",
            "nh3_ppm": round(nh3, 2), "h2s_ppm": round(h2s, 2),
            "vision_label": label, "vision_confidence": round(conf * 100, 1),
            "timestamp": datetime.now(UTC).isoformat()
        }
    elif gas_mild:
        return {
            "isContaminated": False, "status": "MILD GAS CONCERN",
            "badgeClass": "b-warn", "color": "orange",
            "details": f"Elevated gas: NH3={nh3:.2f}ppm, H2S={h2s:.2f}ppm.",
            "nh3_ppm": round(nh3, 2), "h2s_ppm": round(h2s, 2),
            "vision_label": label, "vision_confidence": round(conf * 100, 1),
            "timestamp": datetime.now(UTC).isoformat()
        }
    else:
        return {
            "isContaminated": False, "status": "WATER SAFE & CLEAR",
            "badgeClass": "b-safe", "color": "green",
            "details": "Normal gas levels and water visually clean.",
            "nh3_ppm": round(nh3, 2), "h2s_ppm": round(h2s, 2),
            "vision_label": label, "vision_confidence": round(conf * 100, 1),
            "timestamp": datetime.now(UTC).isoformat()
        }

# ── Firebase Realtime Database Uplink ───────────────────────────────────
def push_node_to_firebase(node_id):
    if not FIREBASE_AUTH or FIREBASE_AUTH == "PASTE_YOUR_DATABASE_SECRET_HERE":
        return
    try:
        path = f"/nodes/node_{node_id}.json?auth={FIREBASE_AUTH}"
        data = node_data.get(node_id)
        if data:
            resp = requests.patch(FIREBASE_URL + path, json=data, timeout=5)
            system_status["firebase"] = resp.ok
    except Exception as e:
        system_status["firebase"] = False
        logger.error(f"Firebase push failed: {e}")

def push_lab_result_to_firebase(verdict):
    if not FIREBASE_AUTH or FIREBASE_AUTH == "PASTE_YOUR_DATABASE_SECRET_HERE":
        return
    try:
        ts = int(time.time())
        path = f"/lab_results/{ts}.json?auth={FIREBASE_AUTH}"
        resp = requests.put(FIREBASE_URL + path, json=verdict, timeout=5)
        system_status["firebase"] = resp.ok
    except Exception as e:
        system_status["firebase"] = False
        logger.error(f"Firebase lab push failed: {e}")

# ── Video Image Classification Callback ─────────────────────────────────
# Camera is ALWAYS running (managed by App.run). We just gate the callback.
def on_video_classifications(classifications):
    global latest_vision, latest_verdict
    if not diagnostic_state["camera_active"]:
        return
    if not classifications:
        return

    best_label = max(classifications, key=classifications.get)
    best_conf = classifications[best_label]

    latest_vision = {
        "label": best_label,
        "confidence": best_conf,
        "classifications": classifications,
        "timestamp": datetime.now(UTC).isoformat()
    }

    latest_verdict = compute_water_verdict(latest_gas, latest_vision)

    ui.send_message("vision_update", message=json.dumps({
        "vision": latest_vision,
        "verdict": latest_verdict
    }))

detection_stream.on_detect_all(on_video_classifications)

# ── Background MCU task runner (non-blocking for LoRa hot path) ─────────
def _fire_bridge_task(method, arg):
    """Run a Bridge.call on a background thread so it never blocks WebUI."""
    def _task():
        try:
            Bridge.call(method, arg)
        except Exception:
            pass
    threading.Thread(target=_task, daemon=True).start()

# ── LoRa CSV Parser & State Updater ────────────────────────────────────
def process_lora_csv(csv_data):
    global active_emergencies
    try:
        fields = [f.strip() for f in str(csv_data).strip().split(",")]
        if len(fields) < 10:
            return

        node_id = int(fields[0])
        if node_id < 1 or node_id > 4:
            return

        lat = float(fields[1])
        lon = float(fields[2])
        ph = float(fields[3])
        tds = float(fields[4])
        turbidity = float(fields[5])
        temperature = float(fields[6])
        waterPresence = fields[7] == "1"
        leakAlert = fields[8] == "1"
        emergencyFlag = fields[9] == "1"
        now_iso = datetime.now(UTC).isoformat()

        # Determine status
        emergencyReason = None
        status = "NORMAL"

        if leakAlert and emergencyFlag:
            emergencyReason = f"Pipe Node {node_id}: Critical Pipe Leak & Contamination!"
            status = "EMERGENCY"
        elif leakAlert:
            emergencyReason = f"Pipe Node {node_id}: Acoustic Pipe Leak Detected!"
            status = "LEAK_ALERT"
        elif emergencyFlag or ph < 6.0 or ph > 8.5 or turbidity > 100.0:
            emergencyReason = f"Pipe Node {node_id}: Contamination (pH={ph:.2f}, Turb={turbidity:.1f})!"
            status = "CONTAMINATION"
        elif ph < 6.5 or ph > 8.0 or tds > 500.0 or turbidity > 50.0:
            status = "WARNING"

        payload = {
            "nodeId":        node_id,
            "name":          node_data[node_id].get("name", f"Pipe Node {node_id}"),
            "latitude":      lat if lat != 0.0 else node_data[node_id]["latitude"],
            "longitude":     lon if lon != 0.0 else node_data[node_id]["longitude"],
            "ph":            round(ph, 2),
            "tds":           round(tds, 1),
            "turbidity":     round(turbidity, 1),
            "temperature":   round(temperature, 1),
            "waterPresence": waterPresence,
            "leakAlert":     leakAlert,
            "emergencyFlag": emergencyFlag,
            "status":        status,
            "emergencyReason": emergencyReason,
            "timestamp":     now_iso,
            "online":        True,
            "hasData":       True
        }

        node_data[node_id] = payload
        system_status["lora_active"] = True
        system_status["last_packet_time"] = now_iso

        # Manage emergencies
        if emergencyReason:
            active_emergencies[node_id] = emergencyReason
            # Trigger buzzer on background thread (non-blocking)
            _fire_bridge_task("buzzer_beep", "3000")
        else:
            active_emergencies.pop(node_id, None)

        # Push Firebase on background thread
        threading.Thread(target=push_node_to_firebase, args=(node_id,), daemon=True).start()

        # Broadcast live update to WebUI immediately (no blocking Bridge calls first)
        ui.send_message("node_update", message=json.dumps(payload))
        ui.send_message("emergency_status", message=json.dumps(list(active_emergencies.values())))
        ui.send_message("system_status", message=json.dumps(system_status))

        logger.info(f"LoRa Pipe Node {node_id}: pH={ph:.2f}, TDS={tds:.1f}, Turb={turbidity:.1f}, Temp={temperature:.1f} | {status}")
    except Exception as e:
        logger.error(f"LoRa parse error: {e}")

# ── Bridge LoRa Notification Handler ────────────────────────────────────
def on_lora_packet(csv_data):
    process_lora_csv(csv_data)

Bridge.provide("lora_packet", on_lora_packet)

# ── LoRa Polling Backup ────────────────────────────────────────────────
def lora_polling_worker():
    while True:
        try:
            raw_csv = Bridge.call("get_latest_lora", "")
            if raw_csv and len(str(raw_csv).strip()) > 0:
                process_lora_csv(str(raw_csv).strip())
        except Exception:
            pass
        time.sleep(0.25)

threading.Thread(target=lora_polling_worker, daemon=True).start()

# ── Gas Sensor Background Polling ───────────────────────────────────────
def gas_polling_worker():
    while True:
        if diagnostic_state["gas_active"]:
            sample_gas_sensors()
        time.sleep(2.0)

threading.Thread(target=gas_polling_worker, daemon=True).start()

def sample_gas_sensors():
    global latest_gas, latest_verdict
    try:
        mq_resp = Bridge.call("read_mq_sensors", "")
        if mq_resp and "," in str(mq_resp):
            parts = str(mq_resp).split(",")
            latest_gas["nh3_ppm"] = float(parts[0])
            latest_gas["h2s_ppm"] = float(parts[1])
            latest_gas["timestamp"] = datetime.now(UTC).isoformat()
    except Exception as e:
        logger.error(f"MQ sensor read failed: {e}")

    latest_verdict = compute_water_verdict(latest_gas, latest_vision)

    if latest_verdict["isContaminated"]:
        threading.Thread(target=push_lab_result_to_firebase, args=(latest_verdict,), daemon=True).start()

    ui.send_message("gas_update", message=json.dumps({
        "gas": latest_gas,
        "verdict": latest_verdict,
        "active": diagnostic_state["gas_active"]
    }))

# ── WebUI WebSocket Event Listeners ─────────────────────────────────────
def handle_initial_state(sid, data=None):
    """Broadcast full state to all connected clients."""
    ui.send_message("initial_state", message=json.dumps({
        "nodes": node_data,
        "gas": latest_gas,
        "vision": latest_vision,
        "verdict": latest_verdict,
        "diagnostics": diagnostic_state,
        "emergencies": list(active_emergencies.values()),
        "system": system_status
    }))

def handle_start_camera_test(sid=None, data=None):
    """Enable classification forwarding. Camera hardware stays running."""
    diagnostic_state["camera_active"] = True
    ui.send_message("camera_status", message=json.dumps({"active": True}))
    logger.info("Camera classification forwarding ENABLED.")

def handle_stop_camera_test(sid=None, data=None):
    """Disable classification forwarding. Camera hardware stays running."""
    diagnostic_state["camera_active"] = False
    ui.send_message("camera_status", message=json.dumps({"active": False}))
    logger.info("Camera classification forwarding DISABLED.")

def handle_start_gas_test(sid=None, data=None):
    diagnostic_state["gas_active"] = True
    sample_gas_sensors()
    ui.send_message("gas_status", message=json.dumps({"active": True}))
    logger.info("Gas sensor polling STARTED.")

def handle_stop_gas_test(sid=None, data=None):
    diagnostic_state["gas_active"] = False
    ui.send_message("gas_status", message=json.dumps({"active": False}))
    logger.info("Gas sensor polling STOPPED.")

def handle_select_node(sid, data):
    try:
        nid = int(data)
        if 1 <= nid <= 4:
            diagnostic_state["selected_node"] = nid
    except Exception:
        pass

def handle_override_threshold(sid, data):
    try:
        th = float(data)
        detection_stream.override_threshold(th)
        logger.info(f"AI confidence threshold updated to {th}")
    except Exception as e:
        logger.error(f"Threshold override error: {e}")

# Register WebUI event listeners
ui.on_message("request_initial_state", handle_initial_state)
ui.on_message("start_camera_test", handle_start_camera_test)
ui.on_message("stop_camera_test", handle_stop_camera_test)
ui.on_message("start_gas_test", handle_start_gas_test)
ui.on_message("stop_gas_test", handle_stop_gas_test)
ui.on_message("select_node", handle_select_node)
ui.on_message("override_threshold", handle_override_threshold)

# ── Start Application ───────────────────────────────────────────────────
logger.info("==================================================")
logger.info("  Jal Rakshak Master Node — App Lab Starting")
logger.info("  Arduino UNO Q | Vision AI + LoRa Central Gateway")
logger.info("  Receiving Telemetry: LoRa 433 MHz from Pipe Nodes")
logger.info("  Forensic Cup: Vision AI + MQ135/MQ136 Gas Fusion")
logger.info("==================================================")

# App.run() manages camera, WebUI, and Bridge lifecycle
App.run()

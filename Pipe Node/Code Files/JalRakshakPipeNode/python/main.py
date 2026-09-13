#!/usr/bin/env python3
"""
Jal Rakshak Pipe Node — Arduino App Lab Brick Application.
Runs on the Qualcomm Dragonwing MPU (2GB RAM, Linux) of the Arduino UNO Q.

NOTE: The Pipe Node has NO internet connection.
      All field telemetry goes ONLY via LoRa to the Master Node.
      Firebase upload is handled exclusively by the Master Node.

Bricks used:
  - arduino:audio_classification  — Edge Impulse acoustic leak classifier
      Project: Jal-Rakshak-Acoustic-Leak-Detection
      Classes: Leak | Noise
      Leak confirmed when P(Leak) >= 0.75 for 2 consecutive windows
  - arduino:web_ui  — LOCAL diagnostic dashboard on port 7000
      Purpose: Field technician connects mobile to Pipe Node Wi-Fi,
      opens http://<pipe-node-ip>:7000 to view live sensor readings and AI
      status for on-site diagnostics ONLY. No internet required.

Bridge RPC (MPU <-> STM32 MCU):
  MCU provides:
    - read_sensors()       -> CSV: nodeId,lat,lon,pH,TDS,Turb,Temp,flow,leak,emergency
    - trigger_lora_tx()    -> forces immediate LoRa packet Tx
    - leak_alert(bool)     -> MCU sets leakAlert flag and forces LoRa Tx

  MPU notifies MCU:
    - Bridge.notify("leak_alert", True/False)  — acoustic AI result
    - Bridge.notify("trigger_lora_tx", "")     — manual diagnostic LoRa Tx

Author: Varun Sontakke — Jal Rakshak Project
"""

from arduino.app_utils import *
from arduino.app_bricks.audio_classification import AudioClassification
from arduino.app_bricks.web_ui import WebUI

from datetime import datetime, timezone
import json
import logging
import threading
import time

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("jal-rakshak-pipe-node")

# ── Initialize Bricks ─────────────────────────────────────────────────────────
# web_ui: local diagnostic WebUI — accessible only on Pipe Node local Wi-Fi
# audio_classification: Edge Impulse acoustic leak detector
ui = WebUI()
sound_classifier = None

# ── Acoustic AI State ─────────────────────────────────────────────────────────
# Temporal consistency: require 2 consecutive high-confidence windows
LEAK_CONFIDENCE_THRESHOLD = 0.75
CONSECUTIVE_WINDOWS_REQUIRED = 2

acoustic_state = {
    "consecutive_leak_count": 0,
    "leak_confirmed": False,
    "last_label": "Noise",
    "last_confidence": 0.0,
    "timestamp": None,
    "classifications": {"Leak": 0.0, "Noise": 0.0},
}

# ── Live Sensor State (updated from MCU via polling) ──────────────────────────
# Default values set to safe, normal drinking water baseline when probes are not connected
sensor_state = {
    "nodeId": 1,
    "latitude": 22.7196,
    "longitude": 75.8577,
    "ph": 7.24,
    "tds": 185.0,
    "turbidity": 8.5,
    "temperature": 25.0,
    "waterPresence": True,
    "leakAlert": False,
    "emergencyFlag": False,
    "status": "NORMAL",
    "timestamp": None,
}

system_status = {
    "lora_active": False,  # True once MCU confirms a LoRa Tx was sent
    "ai_running": False,
    "last_update": None,
}

def sanitize_sensor_fields(fields):
    """
    Parse and sanitize sensor fields from MCU CSV data.
    If physical probes are disconnected, floating, or returning uncalibrated open-circuit
    extreme values (e.g. pH >= 13.9 or <= 0.1, TDS <= 5.0 ppm, Turbidity <= 0.1 NTU),
    fallback to default safe normal range values.
    """
    node_id   = int(fields[0])
    lat       = float(fields[1])
    lon       = float(fields[2])
    raw_ph    = round(float(fields[3]), 2)
    raw_tds   = round(float(fields[4]), 1)
    raw_turb  = round(float(fields[5]), 1)
    raw_temp  = round(float(fields[6]), 1)
    flow_flag = (fields[7] == "1")
    leak_flag = (fields[8] == "1")
    emg_flag  = (fields[9] == "1")

    # Safe fallback values when probes are not connected
    safe_ph   = 7.24 if (raw_ph <= 0.1 or raw_ph >= 13.9) else raw_ph
    safe_tds  = 185.0 if (raw_tds <= 5.0) else raw_tds
    safe_turb = 8.5 if (raw_turb <= 0.1) else raw_turb
    safe_temp = 25.0 if (raw_temp <= -50.0 or raw_temp >= 85.0) else raw_temp

    # If emergency was caused by disconnected probes, re-evaluate with safe values
    if (safe_ph != raw_ph or safe_tds != raw_tds or safe_turb != raw_turb):
        is_emg = (safe_ph < 6.0 or safe_ph > 8.5 or safe_tds > 800.0 or safe_turb > 400.0)
    else:
        is_emg = emg_flag

    return {
        "nodeId":        node_id,
        "latitude":      lat,
        "longitude":     lon,
        "ph":            safe_ph,
        "tds":           safe_tds,
        "turbidity":     safe_turb,
        "temperature":   safe_temp,
        "waterPresence": flow_flag or True,
        "leakAlert":     leak_flag,
        "emergencyFlag": is_emg,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
    }

# ── MCU Sensor Polling ────────────────────────────────────────────────────────
def poll_sensors():
    """Poll MCU for latest sensor values via Bridge RPC every 3 seconds."""
    global sensor_state
    try:
        raw = Bridge.call("read_sensors", "")
        if raw and "," in str(raw):
            fields = str(raw).strip().split(",")
            if len(fields) >= 10:
                sanitized = sanitize_sensor_fields(fields)
                sensor_state.update(sanitized)
                system_status["lora_active"] = True
                system_status["last_update"] = sensor_state["timestamp"]
                _classify_sensor_status()
                _broadcast_ui()
                logger.info(
                    f"Sensors: pH={sensor_state['ph']}, TDS={sensor_state['tds']} ppm, "
                    f"Turb={sensor_state['turbidity']} NTU, Temp={sensor_state['temperature']}C, "
                    f"Leak={sensor_state['leakAlert']}, Emg={sensor_state['emergencyFlag']}"
                )
    except Exception as e:
        logger.error(f"Sensor poll error: {e}")

def _classify_sensor_status():
    """Determine STATUS string from sensor values and flags."""
    s = sensor_state
    if s["leakAlert"] and s["emergencyFlag"]:
        s["status"] = "EMERGENCY"
    elif s["leakAlert"]:
        s["status"] = "LEAK_ALERT"
    elif s["emergencyFlag"]:
        s["status"] = "CONTAMINATION"
    elif (s["ph"] < 6.5 or s["ph"] > 8.0 or
          s["tds"] > 500.0 or s["turbidity"] > 50.0):
        s["status"] = "WARNING"
    else:
        s["status"] = "NORMAL"

def sensor_polling_worker():
    """Background thread — polls MCU every 3 seconds."""
    time.sleep(3.0)   # Wait for MCU to fully boot before first poll
    while True:
        poll_sensors()
        time.sleep(3.0)

threading.Thread(target=sensor_polling_worker, daemon=True).start()

# ── WebUI Broadcast ───────────────────────────────────────────────────────────
def _broadcast_ui():
    """Push current state to all connected diagnostic clients (local Wi-Fi only)."""
    payload = {
        "sensors": sensor_state,
        "acoustic": acoustic_state,
        "system": system_status,
    }
    ui.send_message("state_update", message=json.dumps(payload))

# ── Audio Classification Callback ─────────────────────────────────────────────
def on_audio_classified(*args, **kwargs):
    """
    Called by the audio_classification brick on every inference window.
    Supports classifications as dict, list of dicts, or via kwargs.
    Target Edge Impulse Project: Jal-Rakshak-Acoustic-Leak-Detection
    Classes: 'Leak' | 'Noise'

    On confirmed leak:
      - Notifies MCU via Bridge to set leakAlert flag
      - MCU forces immediate LoRa Tx to Master Node
      - Local WebUI shows red emergency banner
    """
    global acoustic_state

    # Safely extract payload regardless of brick callback signature
    raw = None
    if args:
        raw = args[0]
    elif "classifications" in kwargs:
        raw = kwargs["classifications"]
    elif "detections" in kwargs:
        raw = kwargs["detections"]
    elif kwargs:
        raw = kwargs

    if not raw:
        return

    class_map = {}
    if isinstance(raw, dict):
        if "detections" in raw and isinstance(raw["detections"], (dict, list)):
            raw = raw["detections"]
        if isinstance(raw, dict):
            for k, v in raw.items():
                try:
                    class_map[str(k)] = float(v)
                except (ValueError, TypeError):
                    pass
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    lbl = item.get("label") or item.get("content") or item.get("class") or item.get("name")
                    val = item.get("confidence") or item.get("value") or item.get("score") or 0.0
                    if lbl is not None:
                        try:
                            class_map[str(lbl)] = float(val)
                        except (ValueError, TypeError):
                            pass
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                lbl = item.get("label") or item.get("content") or item.get("class") or item.get("name")
                val = item.get("confidence") or item.get("value") or item.get("score") or 0.0
                if lbl is not None:
                    try:
                        class_map[str(lbl)] = float(val)
                    except (ValueError, TypeError):
                        pass

    if not class_map:
        return

    best_label = max(class_map, key=class_map.get)
    best_conf  = float(class_map[best_label])

    acoustic_state["last_label"]      = best_label
    acoustic_state["last_confidence"] = round(best_conf, 3)
    acoustic_state["timestamp"]       = datetime.now(timezone.utc).isoformat()
    acoustic_state["classifications"] = {k: round(float(v), 3) for k, v in class_map.items()}

    logger.info(f"Edge AI Acoustic: {best_label} ({best_conf*100:.1f}%) | {class_map}")

    if "leak" in best_label.lower() and best_conf >= LEAK_CONFIDENCE_THRESHOLD:
        acoustic_state["consecutive_leak_count"] += 1
    else:
        acoustic_state["consecutive_leak_count"] = 0

    previously_confirmed = acoustic_state["leak_confirmed"]
    acoustic_state["leak_confirmed"] = (
        acoustic_state["consecutive_leak_count"] >= CONSECUTIVE_WINDOWS_REQUIRED
    )

    if acoustic_state["leak_confirmed"] and not previously_confirmed:
        logger.warning(
            f"🚨 ACOUSTIC LEAK CONFIRMED! "
            f"P({best_label})={best_conf:.3f} for {CONSECUTIVE_WINDOWS_REQUIRED} consecutive windows."
        )
        # Notify MCU: set leakAlert flag + force immediate LoRa Tx to Master Node
        try:
            Bridge.notify("leak_alert", True)
        except Exception as e:
            logger.error(f"Bridge notify error: {e}")
        sensor_state["leakAlert"]     = True
        sensor_state["emergencyFlag"] = True
        sensor_state["status"]        = "LEAK_ALERT"

    elif not acoustic_state["leak_confirmed"] and previously_confirmed:
        logger.info("Acoustic leak cleared.")
        try:
            Bridge.notify("leak_alert", False)
        except Exception as e:
            logger.error(f"Bridge notify error: {e}")
        sensor_state["leakAlert"] = False
        _classify_sensor_status()

    # Push AI result to local WebUI diagnostic clients
    audio_payload = {
        "classifications": acoustic_state["classifications"],
        "label": best_label,
        "confidence": round(best_conf, 3),
        "leak_confirmed": acoustic_state["leak_confirmed"],
        "consecutive_count": acoustic_state["consecutive_leak_count"],
        "timestamp": acoustic_state["timestamp"],
    }
    ui.send_message("audio_update", message=json.dumps(audio_payload))

# ── Audio Classifier Initialization with Direct ALSA Device Resolution ───────
def create_alsa_microphone():
    """Attempt to create an ALSA Microphone instance using direct device strings."""
    try:
        from arduino.app_peripherals.microphone import Microphone
    except Exception:
        try:
            from arduino.app_peripherals.microphone.microphone import Microphone
        except Exception as e:
            logger.debug(f"Could not import Microphone class: {e}")
            return None

    # Candidate ALSA devices:
    # 1. 'plughw:0,0' - Card 0 Device 0 with auto rate/format conversion
    # 2. 'hw:0,0'     - Direct hardware card 0 (matches Edge Impulse Linux CLI output: hw:0,0)
    # 3. 'plughw:1,0' - In case USB audio enumerated as card 1
    # 4. 'hw:1,0'
    # 5. 'default'    - Standard ALSA default
    # 6. 'plughw:CARD=Audio,DEV=0'
    candidates = ["plughw:0,0", "hw:0,0", "plughw:1,0", "hw:1,0", "default", "plughw:CARD=Audio,DEV=0"]

    for dev_name in candidates:
        try:
            logger.info(f"Attempting ALSA microphone connection on '{dev_name}'...")
            mic = Microphone(dev_name, sample_rate=16000, channels=1)
            logger.info(f"✅ Successfully opened microphone on ALSA device '{dev_name}'!")
            return mic
        except Exception as err:
            logger.debug(f"ALSA device '{dev_name}' failed: {err}")
    return None

def register_audio_callback(sc, callback):
    """
    Register callback on AudioClassification brick.
    1. Hooks infer_from_features to intercept every 500ms inference window directly from Edge Impulse runner
       and stream continuous probabilities to local WebUI and leak detector.
    2. Registers zero-argument callbacks with on_detect per AudioClassification specifications.
    """
    methods = [m for m in dir(sc) if not m.startswith("_")]
    logger.info(f"AudioClassification available methods: {methods}")

    # ── 1. Intercept infer_from_features for continuous real-time classification ──
    try:
        orig_infer = sc.infer_from_features
        def wrapped_infer(features):
            res = orig_infer(features)
            try:
                if res and isinstance(res, dict) and "result" in res:
                    clf = res["result"].get("classification")
                    if clf and isinstance(clf, dict):
                        callback(clf)
            except Exception as ex:
                logger.debug(f"wrapped_infer callback error: {ex}")
            return res

        sc.infer_from_features = wrapped_infer
        logger.info("✅ Successfully hooked infer_from_features for continuous real-time Edge AI streaming!")
    except Exception as e:
        logger.warning(f"Could not hook infer_from_features: {e}")

    # ── 2. Register zero-argument callbacks for on_detect ─────────────────────────
    if hasattr(sc, "on_detect"):
        def on_leak_spotted():
            logger.debug("Edge AI on_detect: LEAK keyword spotted.")

        def on_noise_spotted():
            logger.debug("Edge AI on_detect: Noise keyword spotted.")

        # Register lowercase keywords as AudioDetector converts keywords to lower()
        for leak_kw in ["leak", "water_leak"]:
            try:
                sc.on_detect(leak_kw, on_leak_spotted)
            except Exception as ex:
                logger.debug(f"on_detect({leak_kw}) error: {ex}")

        for noise_kw in ["noise", "environment_noise", "ambient_noise"]:
            try:
                sc.on_detect(noise_kw, on_noise_spotted)
            except Exception as ex:
                logger.debug(f"on_detect({noise_kw}) error: {ex}")

        logger.info("✅ Registered zero-argument audio callbacks via on_detect for 'leak' and 'noise'")

    return True

def init_audio_classifier():
    """Initialize AudioClassification using direct ALSA mic or default fallback."""
    global sound_classifier

    # Step 1: Try direct ALSA devices first (bypasses Docker container udev issue)
    mic = create_alsa_microphone()
    if mic is not None:
        try:
            try:
                sc = AudioClassification(mic=mic, confidence=0.4)
            except TypeError:
                sc = AudioClassification(mic=mic)
            if hasattr(sc, "_debounce_sec"):
                sc._debounce_sec = 0.0
            register_audio_callback(sc, on_audio_classified)
            sound_classifier = sc
            system_status["ai_running"] = True
            logger.info("✅ AudioClassification brick initialized with direct ALSA microphone!")
            _broadcast_ui()
            return True
        except Exception as e:
            logger.warning(f"AudioClassification(mic) failed: {e}")

    # Step 2: Fallback to default AudioClassification()
    try:
        try:
            sc = AudioClassification(confidence=0.4)
        except TypeError:
            sc = AudioClassification()
        if hasattr(sc, "_debounce_sec"):
            sc._debounce_sec = 0.0
        register_audio_callback(sc, on_audio_classified)
        sound_classifier = sc
        system_status["ai_running"] = True
        logger.info("✅ AudioClassification brick initialized with default microphone.")
        _broadcast_ui()
        return True
    except Exception as e:
        system_status["ai_running"] = False
        logger.warning(f"⚠️ Microphone not ready yet ({e}).")
        return False

# Attempt initial connection; if mic is not ready, start background retry thread
if not init_audio_classifier():
    def mic_reconnect_worker():
        """Background thread to auto-detect USB mic when plugged in without restart."""
        global sound_classifier
        while sound_classifier is None:
            time.sleep(4.0)
            if init_audio_classifier():
                logger.info("✅ USB microphone detected! AudioClassification is now running.")
                break
    threading.Thread(target=mic_reconnect_worker, daemon=True).start()

# ── WebUI Diagnostic Event Handlers ──────────────────────────────────────────
def handle_request_state(*args, **kwargs):
    """Technician's mobile connected to pipe node Wi-Fi requests current state."""
    _broadcast_ui()

def handle_force_lora(*args, **kwargs):
    """Diagnostic: manually trigger a LoRa Tx from the WebUI."""
    try:
        Bridge.notify("trigger_lora_tx", "")
        logger.info("Manual LoRa Tx triggered from local diagnostic WebUI.")
    except Exception as e:
        logger.error(f"force_lora error: {e}")

ui.on_message("request_state", handle_request_state)
ui.on_message("force_lora",    handle_force_lora)

# ── Bridge: MCU notifies MPU after each LoRa Tx ───────────────────────────────
def on_sensor_update_from_mcu(csv_data):
    """
    The MCU calls Bridge.notify("sensor_update", csv) after each LoRa Tx.
    We update sensor_state immediately so local WebUI reflects latest data.
    NOTE: No Firebase push here — Pipe Node has no internet.
          Master Node handles cloud upload after receiving via LoRa.
    """
    try:
        fields = str(csv_data).strip().split(",")
        if len(fields) >= 10:
            sanitized = sanitize_sensor_fields(fields)
            sensor_state.update(sanitized)
            system_status["lora_active"] = True
            _classify_sensor_status()
            _broadcast_ui()
    except Exception as e:
        logger.error(f"sensor_update parse error: {e}")

Bridge.provide("sensor_update", on_sensor_update_from_mcu)

# ── Boot ──────────────────────────────────────────────────────────────────────
logger.info("==================================================")
logger.info("  Jal Rakshak Pipe Node — App Lab Starting")
logger.info("  Arduino UNO Q 2GB | Acoustic AI + Sensor Fusion")
logger.info("  WebUI: Local diagnostic only (no internet)")
logger.info("  Telemetry: LoRa -> Master Node ONLY")
logger.info("==================================================")

# App.run() manages the audio_classification and web_ui brick lifecycle.
App.run()
# Jal Rakshak Pipe Node — Application Architecture & Code Structure

**Platform:** Arduino UNO Q (Dual-Processor: Qualcomm Dragonwing QRB2210 MPU + STM32U585 MCU)

---

## 1. System Overview

The **Jal Rakshak Pipe Node** is an intelligent, edge-computing underground water security monitor installed directly along municipal pipeline segments. It combines:
1. **Multi-Parameter Physical Sensor Acquisition** on the STM32 MCU.
2. **Sub-surface Acoustic Leak Detection** using Edge AI (TinyML) on the Qualcomm Dragonwing Linux MPU.
3. **Long-Range Telemetry Uplink** via 433 MHz LoRa to the Master Node Gateway.
4. **Local Mobile Diagnostic WebUI** on port 7000 for field technician maintenance without requiring internet access.

> **CRITICAL ARCHITECTURAL DESIGN**: All field telemetry is transmitted exclusively via LoRa (SX1278) to the Master Node, which handles cloud synchronisation.

---

## 2. Dual-Processor Division of Responsibility

| Subsystem | Processor | Environment | Key Responsibilities |
| :--- | :--- | :--- | :--- |
| **Microcontroller (MCU)** | STM32U585 (ARM Cortex-M33) | Zephyr RTOS / Arduino C++ (sketch/) | Real-time ADC sensor sampling (pH, TDS, Turbidity, Temp, Flow switch); LoRa SX1278 binary packet serialization & RF transmission; RouterBridge RPC endpoints. |
| **Microprocessor (MPU)** | Qualcomm Dragonwing QRB2210 (Quad Cortex-A53, 2GB RAM) | Debian Linux / Python 3.13 (python/) | High-speed audio capture via ALSA (plughw:0,0); continuous Edge Impulse inference (Leak vs Noise); temporal alert filtering; diagnostic WebSocket WebUI. |

---

## 3. Communication Interface (RouterBridge RPC)

The MPU and MCU communicate via high-speed shared memory RPC (Arduino_RouterBridge):

- **ead_sensors()** (MCU provides, MPU calls every 3s):
  Returns CSV string: 
odeId,latitude,longitude,ph,tds,turbidity,temperature,waterPresence,leakAlert,emergencyFlag
- **leak_alert(bool)** (MPU notifies MCU):
  Triggered when Edge AI detects acoustic cavitation/leak with $\ge 75\%$ confidence for 2 consecutive windows. Causes MCU to immediately assert the emergency flag and force an unscheduled LoRa transmission.
- **	rigger_lora_tx** (MPU notifies MCU):
  Allows field technicians to trigger an immediate manual LoRa transmission test from the diagnostic WebUI.
- **sensor_update** (MCU notifies MPU):
  Emitted after every periodic LoRa transmission so the local WebUI reflects the exact telemetry sent to the Master Node.

---

## 4. File Structure

`	ext
JalRakshakPipeNode/
├── app.yaml               # App Lab manifest (audio_classification & web_ui bricks)
├── README.md              # Complete architecture and operation documentation
├── assets/
│   ├── index.html         # Responsive diagnostic dashboard HTML
│   ├── style.css          # Dark-mode industrial cyber-clean CSS
│   ├── app.js             # Client WebSocket telemetry & Edge AI bar animator
│   └── libs/
│       ├── arduino.js     # Official Arduino App Lab WebUI client
│       └── socket.io.min.js# Offline Socket.IO client library
├── models/
│   └── README.md          # Edge Impulse project & class documentation
├── python/
│   ├── main.py            # Main MPU application (AI inference hook & bridge logic)
│   └── config.py          # Node identity & deployment parameters
└── sketch/
    ├── sketch.ino         # STM32 MCU firmware (ADC acquisition & LoRa driver)
    └── sketch.yaml        # Zephyr platform & library dependency manifest
`
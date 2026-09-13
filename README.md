# 💧 Jal Rakshak: AI-Powered Municipal Water Security & Pipeline Integrity Network

**Jal Rakshak** ("Water Protector") is a decentralized, dual-tier physical AI water security and acoustic leak detection system designed to safeguard municipal drinking water distribution networks against underground transit contamination, sewage cross-ingress, and silent pipeline bursts.

Addressing the critical "last-mile" vulnerability between centralized water treatment plants and residential taps, Jal Rakshak continuously monitors subterranean pipes using autonomous edge nodes and provides municipal field engineers with a handheld AI diagnostic gateway terminal.

---

## 📌 System Architecture & Core Concept

Municipal water networks frequently suffer from negative pressure events, soil shifting, and aging infrastructure. When an underground potable water pipe develops a leak adjacent to a sewage line or open drain, contaminated water is siphoned into the drinking supply.

Jal Rakshak eliminates reliance on delayed manual complaints and sporadic lab tests through a two-tier physical AI architecture:

```text
+-------------------------------------------------------------------------+
|                      Underground Pipe Node (Field)                      |
|  - ESP32 Dual-Core Controller (Solar / Battery / Energy Harvesting)     |
|  - INMP441 I2S Microphone -> TinyML 1D-CNN (Acoustic Leak Detection)    |
|  - Multi-Sensor Array: pH, Temp-Compensated TDS, Turbidity, Temp, Flow  |
|  - SX1278 LoRa Transceiver (433 MHz Binary Telemetry Uplink)            |
+-------------------------------------------------------------------------+
                                    │
                         [ 433 MHz LoRa Radio Link ]
                         [ 28-Byte Packed Struct   ]
                                    │
                                    ▼
+-------------------------------------------------------------------------+
|                  Jal Rakshak Master Node (Central Gateway)              |
|                                                                         |
|  [STM32U585 MCU (Zephyr RTOS)]                                          |
|   - Hard Real-Time LoRa Telemetry Ingestion (SX1278 SPI)                |
|   - Dual Gas Sensing (12-bit ADC): MQ135 (NH3) & MQ136 (H2S)            |
|   - Hardware Alert Buzzer & RouterBridge Inter-Core RPC Server          |
|                                                                         |
|  [Qualcomm Dragonwing Linux MPU (Arduino App Lab)]                      |
|   - Edge Impulse Vision-AI Image Classifier (MobileNet EIM)             |
|   - Forensic Testing Cup: UV Fluorescence Analysis                      |
|   - Water Quality Multi-Parametric Safety Verdict Engine                |
|   - Interactive WebUI Dashboard on Port 7000 (Leaflet GIS + Live Charts)|
+-------------------------------------------------------------------------+
```

---

## 🧠 Dual Edge AI Intelligence

Jal Rakshak runs two dedicated machine learning models trained via Edge Impulse directly on edge hardware:

1. **TinyML Acoustic Leak Detection (Pipe Node):**
   - **Hardware:** ESP32 (Core 0, FreeRTOS).
   - **Input:** 16 kHz acoustic vibration stream from an INMP441 I2S MEMS microphone clamped to the pipeline.
   - **Model:** 1D-CNN with MFE/MFCC feature extraction distinguishing background urban traffic noise from the high-frequency acoustic hiss of a pressurized pipe leak.
   - **Latency & Performance:** <20 ms inference latency with high energy efficiency on battery power.

2. **Vision-AI Water Quality Classification (Master Node):**
   - **Hardware:** Qualcomm Dragonwing Linux MPU on the Arduino UNO Q.
   - **Input:** Live camera feed from an enclosed testing cup under controlled UV illumination.
   - **Model:** MobileNet transfer-learning vision classifier (`Jal-Rakshak-Water-Quality-Vision`) deployed as a Linux aarch64 EIM executable.
   - **Function:** Detects organic sewage fluorescence, turbidity shifts, and visible contamination that standard electrochemical probes cannot identify.

---

## 📁 Project Structure & File Guide

The repository is organized by subsystem, hardware engineering files, AI models, and documentation assets:

```text
Jal Rakshak/
├── README.md                           # This project documentation
├── Edge AI Models/                     # Standalone compiled Edge Impulse model artifacts (.eim)
├── Images/                             # Architecture diagrams, flowcharts, and hardware photos
├── Master Node/                        # Arduino UNO Q Gateway & Diagnostic Terminal workspace
├── Pipe Node/                          # Underground monitoring node workspace
└── Video/                              # Demonstrations and AI training process recordings
```

### 1. `Master Node/` (Central Gateway & Field Terminal)
* **`Code Files/Master Node APP/`**: Complete Arduino App Lab application for the Arduino UNO Q:
  * `app.yaml`: App Lab application manifest specifying the Python base environment and Edge Impulse video classification brick (`ei-model-1087722-1`).
  * `python/main.py`: Central coordination server, RouterBridge RPC client, multi-sensor verdict logic, and WebSocket broadcaster.
  * `python/config.py`: Thresholds for WHO drinking water standards (pH, TDS, Turbidity, NH₃, H₂S), pinouts, and network configurations.
  * `sketch/sketch.ino`: High-performance Zephyr RTOS firmware for the STM32U585 MCU. Handles SX1278 LoRa reception, MQ135/MQ136 gas ADC sampling, active buzzer alert control, and RouterBridge RPC endpoints.
  * `sketch/sketch.yaml`: Arduino sketch dependency configuration specifying platform and libraries.
  * `assets/`: Web dashboard frontend (`index.html`, `style.css`, `app.js`) featuring real-time GIS pipe map, live telemetry graphs, and forensic testing cup controls.
* **`Code Files/Master Node APP.zip`**: Compressed App Lab package ready for direct import into the Arduino App Lab IDE.
* **`PCB Files/`**:
  * `Schematic_Jal-Rakshak-Master-Node_2026-09-11.png`: Complete Master Node electrical schematic.
  * `PCB_Jal Rakshak Master node.png`: Board layout and trace routing diagram.
  * `Jal Rakshak master Node PCB traces to print.pdf`: Printable 1:1 scale PCB artwork for chemical etching.
* **`CAD Files/`**:
  * `Jal Rakshak Master Node Case.3mf`: 3D printable chassis for the Arduino UNO Q, testing cup chamber, and sensor mountings.
  * `Master Node CAD image.png`, `Slicing SS1.png`, `Slicing SS2.png`: 3D renders and slicer configurations.
* **`Steps to assembly/`**: Step-by-step photographic assembly guide (1.jpeg – 14.jpeg, PCB photos) for component soldering, wiring, and enclosure fitting.
* **`Master Node components.jpeg`**: Photographic overview of all Master Node hardware components.

### 2. `Pipe Node/` (Underground Sensing Station)
* **`Code Files/JalRakshakPipeNode/`**:
  * `sketch/sketch.ino`: ESP32 firmware integrating the Edge Impulse acoustic inference library, analog sensor acquisition (pH, TDS, Turbidity, DS18B20 1-Wire temperature), optical water presence sensing, and 28-byte binary LoRa transmission.
  * `sketch/sketch.yaml`: Dependency configuration for the ESP32 platform.
* **`Code Files/JalRakshakPipeNode.zip`**: Ready-to-deploy archive of the Pipe Node firmware.
* **`PCB Files/`**:
  * `Schematic_Jal-Rakshak-Pipe-Node_2026-09-11.png`: Sensor integration and power management schematic.
  * `Sensor PCB Front.jpg` & `Sensor PCB Back.jpg`: High-resolution photographs of the custom double-sided sensor conditioning board.
* **`CAD Files/`**:
  * `Pipe Node sensor case Final Design.3mf`: In-pipe waterproof sensor chamber for water immersion probes.
  * `Pipe_Node_PCB and MIC Case.3mf`: External acoustic clamp housing holding the ESP32, LoRa module, and INMP441 microphone against the pipe wall.
  * `Pipe Node Sensor Case.png`, `Pipe node Case .png`, `Slicing SS 1.png`, `Slicing SS 2.png`: 3D CAD visualizations and slicing guidelines.
* **`Sound data/`**:
  * `water leak sounds/`: Recorded audio dataset of pressurized water pipe pinhole and crack leaks used for model training.
  * `Noise/`: Environmental baseline recordings (traffic noise, soil dampening, motor hums) used for negative training samples.
* **`Steps to assembly/`**: Comprehensive assembly photographic log (1.jpeg – 20.jpeg, EdgeAI setup guides) showing probe sealing, pipe clamp mounting, and PCB assembly.
* **`Pipe Node Componenets.jpeg` & `Pipe Node sensors.jpeg`**: Visual inventory of all Pipe Node electronics, probes, and mechanical hardware.

### 3. `Edge AI Models/`
* **`jal-rakshak-acoustic-leak-detection-linux-aarch64-v12-impulse-#1.eim`**: Edge Impulse acoustic classification model compiled for aarch64 Linux systems.
* **`jal-rakshak-water-quality-vision-linux-aarch64-v3-impulse-#1.eim`**: Edge Impulse vision classification model compiled for the Qualcomm Dragonwing MPU on the Arduino UNO Q.

### 4. `Images/`
* High-resolution system diagrams and visuals:
  * `Jal_Rakshak_System_Architecture_v3.jpg`: Full end-to-end hardware and network architecture diagram.
  * `Jal_Rakshak_Master_Node_Code_Flowchart.jpg` / `.png`: Operational flow of the dual-processor Master Node firmware and Python runtime.
  * `Jal_Rakshak_Pipe_Node_Code_Flowchart.jpg`: Sensing, TinyML inference, and LoRa transmission logic of the Pipe Node.
  * `Bhagirathpura.png`, `pipeblast.png`, `pipeblast3.png`: Ground truth case study photos demonstrating urban pipeline failure mechanisms.
  * `lorapic.jpg`, `USBc Mic.png`, `Usb C hub.png`, `usb cam.png`, `Data collectionsetup MN.jpeg`: Peripheral and lab testing setup photos.

### 5. `Video/`
* **`Master Node Edge AI making.mp4`**: Demonstration of the Master Node testing cup setup, camera alignment, and Edge Impulse model deployment.
* **`Pipe Node Edge AI Data Collection Process.mp4`**: Acoustic data recording methodology, sensor pod immersion testing, and model training workflow.

---

## 🔌 Hardware Bill of Materials (BOM)

| Subsystem | Component | Specifications / Role |
|---|---|---|
| **Master Gateway** | **Arduino UNO Q (ABX00087)** | Dual-core processor: STM32U585 MCU (Cortex-M33) + Qualcomm Dragonwing Linux MPU |
| **Master Gateway** | **SX1278 LoRa Module (Ra-01)** | 433 MHz SPI LoRa transceiver for long-range packet reception |
| **Master Gateway** | **USB 2.0 HD Camera** | Testing Cup Vision-AI sample image acquisition |
| **Master Gateway** | **UV LED Array (395–405 nm)** | Fluorescent excitation of organic sewage matter |
| **Master Gateway** | **MQ135 Gas Sensor** | Airborne Ammonia ($NH_3$) and sewage gas marker detection |
| **Master Gateway** | **MQ136 Gas Sensor** | Hydrogen Sulfide ($H_2S$) toxic sewage gas detection |
| **Master Gateway** | **5V Active Buzzer** | High-decibel audible emergency alarm for contamination alerts |
| **Pipe Node** | **ESP32 Development Board** | 240 MHz dual-core microcontroller with FreeRTOS |
| **Pipe Node** | **INMP441 I2S MEMS Mic** | Ultra-low noise digital microphone clamped to pipe wall for acoustic leak sensing |
| **Pipe Node** | **SX1278 LoRa Module (Ra-01)** | 433 MHz SPI LoRa transceiver for subterranean packet transmission |
| **Pipe Node** | **Analog pH Sensor & Probe** | Electrochemical hydrogen-ion activity measurement (0–14 pH) |
| **Pipe Node** | **Analog TDS Sensor Kit** | Total Dissolved Solids / mineral conductivity measurement (0–1000 ppm) |
| **Pipe Node** | **Optical Turbidity Sensor** | Nephelometric suspended particulate detection (0–3000 NTU) |
| **Pipe Node** | **DS18B20 Temp Sensor** | Stainless-steel waterproof 1-Wire sensor for dynamic TDS temperature compensation |
| **Pipe Node** | **Optical Liquid Level Sensor** | Non-invasive verification of water presence vs. air-pocket dry conditions |
| **Power** | **3.7V 18650 / LiPo Cells + Solar** | Lithium battery buffering paired with solar/mini-hydro energy harvesting |
| **Enclosures** | **Custom 3D-Printed Housings** | In-pipe water-sealed sensor chamber & external acoustic clamp chassis |

---

## 🚀 Deployment & Operation

### 1. Flashing the Underground Pipe Node (ESP32)
1. Open the Arduino IDE and ensure the **ESP32 by Espressif Systems** board package is installed.
2. Open the sketch located at:
   ```text
   Pipe Node/Code Files/JalRakshakPipeNode/sketch/sketch.ino
   ```
3. Install required libraries via the Arduino Library Manager:
   - `LoRa` (by Sandeep Mistry)
   - `OneWire` & `DallasTemperature`
   - Edge Impulse inferencing library
4. Select board **ESP32 Dev Module**, verify GPIO connections to the sensors and LoRa transceiver, and flash over USB.

### 2. Running the Master Node (Arduino UNO Q)
1. Connect the **Arduino UNO Q** to your local network via Wi-Fi or Ethernet.
2. Launch **Arduino App Lab** and open the application directory:
   ```text
   Master Node/Code Files/Master Node APP
   ```
3. Arduino App Lab automatically parses `app.yaml`, launches the `python-apps-base` container, and initialises the `ei-models-runner` container with the Edge Impulse vision model.
4. The STM32U585 sketch (`sketch/sketch.ino`) is automatically compiled and uploaded to the MCU over the internal bridge.
5. Open your web browser on any device on the same local network:
   ```text
   http://<arduino-uno-q-ip>:7000
   ```
6. The dashboard displays real-time telemetry from up to 4 pipe nodes, live gas concentration values, and interactive controls for the forensic water testing cup.

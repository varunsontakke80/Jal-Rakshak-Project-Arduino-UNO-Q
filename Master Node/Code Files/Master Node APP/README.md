# 💧 Jal Rakshak Master Node : Decentralized Water Quality Monitoring System
## Master Node Application — Arduino App Lab Bricks

> Real-Time Water Quality Forensic Gateway & Underground Pipeline Network Monitor.  

---

## 🌟 Overview & Features

This project connects the **Qualcomm Dragonwing MPU (Linux)** and **STM32U585 MCU** on the Arduino UNO Q with containerized App Lab Bricks:

1. **`arduino:video_image_classification` Brick**:
   - Runs live video classification using your custom Edge Impulse trained model (`good_water` vs `bad_water`).
   - Streams live camera video feed directly on port `4912` (`/embed`) with bounding boxes/classification overlays.
2. **`arduino:web_ui` Brick**:
   - Hosts a mobile-responsive WebSocket dashboard directly on port `7000` from `assets/`.
   - Access from your smartphone, tablet, or PC browser: `http://<board-ip>:7000`.
3. **Dual-Core STM32 MCU & RouterBridge**:
   - **LoRa 433 MHz** receiver for Pipe Nodes 1–4 telemetry (pH, TDS, turbidity, temperature, leak acoustic alert, emergency flags).
   - **MQ135 (NH₃)** and **MQ136 (H₂S)** gas sensors for biochemical sewage contamination detection.
   - **Buzzer** alarm control.
4. **Google Firebase Realtime Database**:
   - Real-time cloud synchronization for pipeline nodes and forensic water test logs.

---

## 📱 Mobile Web Access (Same WiFi)

1. Connect your phone or laptop to the same WiFi network as your Arduino UNO Q.
2. Open your mobile browser and navigate to:
   ```
   http://<board-ip>:7000
   ```
   *(Example: `http://192.168.1.50:7000` or `http://arduino-uno-q.local:7000`)*

---

## 📁 Project Structure

```
Master Node APP/
├── app.yaml               # App Lab manifest (declares video_image_classification & web_ui bricks)
├── README.md              # Project documentation and deployment guide
│
├── sketch/                # MCU Firmware (STM32U585)
│   ├── sketch.ino         # LoRa SX1278 (433MHz), MQ135/136 ADC, Buzzer, RouterBridge
│   └── sketch.yaml        # Board profile (arduino:zephyr) and pinned library dependencies
│
├── python/                # MPU Application (Qualcomm Dragonwing Linux)
│   ├── main.py            # App Lab Bricks coordinator, RouterBridge listener, Firebase uplink, App.run()
│   ├── config.py          # Firebase Realtime Database credentials
│   └── requirements.txt   # Python dependencies (requests)
│
├── assets/                # WebUI Brick Frontend (served on Port 7000)
│   ├── index.html         # Responsive tabbed dashboard (Pipe Nodes, Water Cup Test, Diagnostics)
│   ├── style.css          # Dark-theme mobile-first stylesheet
│   ├── app.js             # WebUI client (WebSocket events, threshold slider, gas trigger)
│   ├── libs/
│   │   ├── arduino.js     # Official Arduino WebUI client SDK
│   │   └── socket.io.min.js
│   └── img/               # Icons and graphics
│
└── models/                # Edge Impulse ML Models
    └── auqtest-linux-aarch64-v1-impulse-#1.eim   # Custom water quality model
```

---

## 🔌 Hardware Wiring & Pin Mapping

| Peripheral | Board Pin | Type | Function |
|---|---|---|---|
| **LoRa SCK** | D13 | SPI | SX1278 SPI Clock |
| **LoRa MISO** | D12 | SPI | SX1278 SPI MISO |
| **LoRa MOSI** | D11 | SPI | SX1278 SPI MOSI |
| **LoRa CS (NSS)** | D10 | GPIO | Chip Select |
| **LoRa RST** | D9 | GPIO | Reset |
| **LoRa DIO0** | D2 | GPIO (Interrupt) | Packet Received Flag |
| **MQ135 (Ammonia)** | A0 | Analog ADC (3.3V) | NH₃ Gas Sensor (via 10k/20k divider) |
| **MQ136 (H₂S)** | A1 | Analog ADC (3.3V) | H₂S Gas Sensor (via 10k/20k divider) |
| **Buzzer** | D7 | Digital Output | Active Alarm (HIGH = ON) |
| **USB Camera** | USB-C Hub | V4L2 USB | Water Testing Cup Visual AI |

> ⚠️ **Voltage Note**: The STM32U585 GPIOs operate at **3.3V**. Ensure MQ sensors use the 10kΩ + 20kΩ voltage divider from the 5V sensor output.

---

## 🚀 How to Run in Arduino App Lab

### Step 1 — Open the App in App Lab IDE
1. Connect your **Arduino UNO Q** to your computer via USB-C.
2. Launch the **Arduino App Lab** application.
3. Click **Open App** and select the `Master Node APP` folder.

### Step 2 — Model Setup
- In App Lab, the `app.yaml` will automatically detect the `video_image_classification` Brick.
- You can select your imported Edge Impulse water model (`auqtest-linux-aarch64-v1-impulse-#1`) in the brick settings.

### Step 3 — Configure Cloud Database
- Edit `python/config.py` with your Firebase Realtime Database URL & secret key.

### Step 4 — Run!
- Click the **Run** button at the top of App Lab.
- App Lab compiles the MCU sketch, launches the Brick containers, and opens the Web UI.
- On your phone, visit `http://<board-ip>:7000` to interact with the system live!

# Jal Rakshak Pipe Node — Edge AI Acoustic Leak Detection Model

This folder documents the Edge Impulse model configuration for the underground acoustic leak detection system running on the Arduino UNO Q (Qualcomm Dragonwing QRB2210 MPU, Linux aarch64).

---

## 1. Edge Impulse Project Details

- **Project Name:** Jal-Rakshak-Acoustic-Leak-Detection
- **Owner / Project ID:** arunsontakke80 / 1022382
- **Deployment Version:** 11 (ei-model-1022382-1)
- **Application:** Real-time acoustic frequency analysis of pipe vibrations to detect subterranean water leaks and cavitation
- **Target Hardware:** Arduino UNO Q (Qualcomm Dragonwing QRB2210, Linux aarch64)
- **Input Peripheral:** USB Microphone on ALSA hardware card plughw:0,0

---

## 2. Model Classes & Classification

The trained model classifies 1-second audio windows into 2 distinct classes:

| Class | Label in EI | Description | System Action |
|-------|-------------|-------------|---------------|
| **1** | Leak | Acoustic signature of pressurized water escaping a pipe fissure, cavitation hiss, or turbulent pipe breach | Increment consecutive counter; trigger emergency LoRa packet when confidence >= 75% for 2 consecutive windows |
| **2** | Noise | Normal ambient background sound, pump hum, laminar water flow, or surface environmental noise | Clear leak alert status; maintain normal telemetry cycle |

---

## 3. Impulse Design Parameters

- **Time series data:** 1000 ms (1.0 s) window size, 500 ms sliding window stride
- **Frequency:** 16,000 Hz (16 kHz), 1 channel (mono)
- **Input Features:** 16,000 features per inference window
- **DSP Block:** MFE (Mel-Frequency Energy)
- **Learning Block:** 1D / 2D Convolutional Neural Network (continuous audio classification)

---

## 4. App Lab Architecture & Continuous Inference

In Arduino App Lab, the rduino:audio_classification brick:
1. Automatically launches the Edge Impulse runner container (ei-audio-classifier-runner:1337).
2. Streams audio captured from ALSA plughw:0,0 (16 kHz mono) into the model.
3. python/main.py hooks sc.infer_from_features to intercept every single inference slice (~400 ms) directly from the runner.
4. Raw probabilities for both Leak and Noise are streamed in real time over WebSocket to the local diagnostic WebUI (http://<ip>:7000).
5. When Leak >= 0.75 for 2 consecutive windows, python/main.py notifies the STM32 MCU via Bridge RPC (leak_alert), forcing an immediate emergency LoRa transmission to the Master Node.
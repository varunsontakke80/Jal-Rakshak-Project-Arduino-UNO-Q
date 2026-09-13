/**
 * Jal Rakshak Master Node — Arduino UNO Q (STM32U585 MCU, Zephyr RTOS)
 * 
 * Responsibilities (MCU side):
 *   - Receives 28-byte binary TelemetryPayload from Pipe Nodes over LoRa (SX1278, 433 MHz)
 *   - Reads biochemical gas sensors: MQ135 (NH3 on A0), MQ136 (H2S on A1) for testing cup
 *   - Controls buzzer alert (D7) for contamination & leak alarms
 *   - Communicates with Dragonwing Linux MPU via RouterBridge (MessagePack RPC & notify)
 *
 * Author: Varun Sontakke — Jal Rakshak Project
 */

#include <SPI.h>
#include <LoRa.h>
#include <Arduino_RouterBridge.h>

// Arduino UNO Q LoRa RA01 Pinout (standard SPI headers)
#define LORA_SCK  13
#define LORA_MISO 12
#define LORA_MOSI 11
#define LORA_CS   10
#define LORA_RST  9
#define LORA_DIO0 2

#define PIN_MQ135 A0
#define PIN_MQ136 A1
#define PIN_BUZZER 7

// ADC & voltage config for raw gas sensor reading
#define VOLTAGE_RESOLUTION 3.3
#define ADC_MAX 4095.0  // 12-bit ADC

// MQ sensor calibration constants (clean air Rs/Ro ratios)
#define MQ135_RL 10.0   // Load resistance in kΩ
#define MQ135_RO 76.63  // Clean air resistance (calibrated)
#define MQ136_RL 10.0
#define MQ136_RO 19.78

#pragma pack(push, 1)
struct TelemetryPayload {
    uint8_t  nodeId;
    float    latitude;
    float    longitude;
    float    ph;
    float    tds;
    float    turbidity;
    float    temperature;
    bool     waterPresence;
    bool     leakAlert;
    bool     emergencyFlag;
};
#pragma pack(pop)

// Non-blocking 3-second buzzer timer
unsigned long buzzerEndTime = 0;
bool buzzerActive = false;

// Buffer for LoRa telemetry polling backup
String latestLoraCsv = "";
bool hasNewLora = false;

void triggerBuzzer(int durationMs) {
    digitalWrite(PIN_BUZZER, HIGH);
    buzzerEndTime = millis() + durationMs;
    buzzerActive = true;
}

void buzzer_control_handler(bool state) {
    if (state) {
        triggerBuzzer(3000);
    } else {
        digitalWrite(PIN_BUZZER, LOW);
        buzzerActive = false;
    }
}

void buzzer_beep_handler(int durationMs) {
    if (durationMs <= 0) durationMs = 3000;
    triggerBuzzer(durationMs);
}

// ── Raw MQ Gas Sensor Reading (No MQUnifiedsensor library) ──────────
// Converts raw ADC reading to sensor resistance Rs
float getResistance(int pin, float rl) {
    int raw = analogRead(pin);
    if (raw == 0) raw = 1; // prevent divide-by-zero
    float voltage = (float)raw / ADC_MAX * VOLTAGE_RESOLUTION;
    float rs = rl * (VOLTAGE_RESOLUTION - voltage) / voltage;
    return rs;
}

// MQ135: NH3 ppm estimation from Rs/Ro ratio
// Using power regression: ppm = A * (Rs/Ro)^B
// Coefficients for NH3: A=102.2, B=-2.473
float readNH3() {
    float rs = getResistance(PIN_MQ135, MQ135_RL);
    float ratio = rs / MQ135_RO;
    if (ratio <= 0.0) return 0.0;
    float ppm = 102.2 * pow(ratio, -2.473);
    if (ppm < 0.0) ppm = 0.0;
    if (ppm > 500.0) ppm = 500.0; // Clamp to sensor max
    return ppm;
}

// MQ136: H2S ppm estimation from Rs/Ro ratio
// Coefficients for H2S: A=40.5, B=-2.15
float readH2S() {
    float rs = getResistance(PIN_MQ136, MQ136_RL);
    float ratio = rs / MQ136_RO;
    if (ratio <= 0.0) return 0.0;
    float ppm = 40.5 * pow(ratio, -2.15);
    if (ppm < 0.0) ppm = 0.0;
    if (ppm > 200.0) ppm = 200.0;
    return ppm;
}

String read_mq_sensors(String args) {
    float nh3 = readNH3();
    float h2s = readH2S();
    return String(nh3, 2) + "," + String(h2s, 2);
}

String get_latest_lora(String args) {
    if (hasNewLora) {
        hasNewLora = false;
        return latestLoraCsv;
    }
    return "";
}

void setup() {
    Serial.begin(115200);
    delay(2000);
    
    Serial.println("\n========================================");
    Serial.println(" Jal Rakshak Master Node — Starting ");
    Serial.println("========================================");
    
    Bridge.begin();
    
    pinMode(PIN_BUZZER, OUTPUT);
    digitalWrite(PIN_BUZZER, LOW);
    
    // LoRa initialization
    LoRa.setPins(LORA_CS, LORA_RST, LORA_DIO0);
    if (!LoRa.begin(433E6)) {
        Serial.println("Starting LoRa failed! Check Wiring.");
    } else {
        Serial.println("LoRa initialized successfully on 433 MHz.");
    }
    
    analogReadResolution(12);

    // Register Bridge RPC handlers
    Bridge.provide("read_mq_sensors", read_mq_sensors);
    Bridge.provide_safe("buzzer_control", buzzer_control_handler);
    Bridge.provide_safe("buzzer_beep", buzzer_beep_handler);
    Bridge.provide("get_latest_lora", get_latest_lora);
    
    Serial.println("Bridge RPC handlers registered.");
}

void loop() {
    // Non-blocking buzzer timer check
    if (buzzerActive && millis() >= buzzerEndTime) {
        digitalWrite(PIN_BUZZER, LOW);
        buzzerActive = false;
    }

    int packetSize = LoRa.parsePacket();
    if (packetSize > 0) {
        Serial.print("\n[LoRa RX] Packet received, size: ");
        Serial.println(packetSize);
        
        if (packetSize == sizeof(TelemetryPayload)) {
            TelemetryPayload payload;
            LoRa.readBytes((uint8_t*)&payload, sizeof(TelemetryPayload));
            
            Serial.println("====================================");
            Serial.print("Node ID   : "); Serial.println(payload.nodeId);
            Serial.print("GPS Lat   : "); Serial.println(payload.latitude, 6);
            Serial.print("GPS Lon   : "); Serial.println(payload.longitude, 6);
            Serial.print("pH        : "); Serial.println(payload.ph, 2);
            Serial.print("TDS       : "); Serial.print(payload.tds, 2); Serial.println(" ppm");
            Serial.print("Turbidity : "); Serial.print(payload.turbidity, 2); Serial.println(" NTU");
            Serial.print("Temp      : "); Serial.print(payload.temperature, 2); Serial.println(" C");
            Serial.print("Water     : "); Serial.println(payload.waterPresence ? "Yes" : "No");
            Serial.print("Leak Alert: "); Serial.println(payload.leakAlert ? "DETECTED!" : "Clear");
            Serial.print("Emergency : "); Serial.println(payload.emergencyFlag ? "ACTIVE!" : "Normal");
            Serial.println("====================================");
            
            // Format CSV payload for Bridge notification
            String csv = String(payload.nodeId) + "," +
                         String(payload.latitude, 6) + "," +
                         String(payload.longitude, 6) + "," +
                         String(payload.ph, 2) + "," +
                         String(payload.tds, 2) + "," +
                         String(payload.turbidity, 2) + "," +
                         String(payload.temperature, 2) + "," +
                         String(payload.waterPresence ? 1 : 0) + "," +
                         String(payload.leakAlert ? 1 : 0) + "," +
                         String(payload.emergencyFlag ? 1 : 0);
            
            latestLoraCsv = csv;
            hasNewLora = true;
            
            Bridge.notify("lora_packet", csv);
            
            // Auto trigger 3s buzzer on emergency flag or leak
            if (payload.emergencyFlag || payload.leakAlert) {
                triggerBuzzer(3000);
            }
        } else {
            Serial.print("Warning: Expected size ");
            Serial.print(sizeof(TelemetryPayload));
            Serial.print(", but got ");
            Serial.println(packetSize);
        }
    }
    
    delay(10);
}

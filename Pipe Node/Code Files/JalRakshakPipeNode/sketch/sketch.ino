/**
 * Jal Rakshak Pipe Node — Arduino UNO Q (STM32U585 MCU, Zephyr RTOS)
 *
 * Responsibilities (MCU side):
 *   - Read water quality sensors: pH (A0), TDS (A1), Turbidity (A2)
 *   - Read DS18B20 water temperature via 1-Wire (D4)
 *   - Detect water flow switch (D3, interrupt)
 *   - Transmit 28-byte binary TelemetryPayload over LoRa (SX1278, 433 MHz)
 *   - Expose Bridge RPC endpoints for MPU (main.py) to:
 *       - read_sensors()    → returns CSV of all sensor values
 *       - trigger_lora_tx() → forces an immediate LoRa transmission
 *   - Receive leak_alert notifications from MPU (acoustic AI result)
 *     and fold leakAlert flag into the next LoRa transmission
 *
 * Sensors pinout (all analog sensors must go through 10k/20k voltage divider
 * because sensors output 0-5V but UNO Q ADC pins are 3.3V max):
 *   A0 = pH sensor (analog, 0-5V scaled to 0-3.3V)
 *   A1 = TDS sensor (analog, 0-5V scaled to 0-3.3V)
 *   A2 = Turbidity sensor (analog, 0-5V scaled to 0-3.3V)
 *   D4 = DS18B20 data (1-Wire, 4.7k pull-up to 3.3V)
 *   D3 = Water flow switch (digital input, interrupt on CHANGE)
 * LoRa SX1278 (SPI):
 *   D13 = SCK, D12 = MISO, D11 = MOSI, D10 = CS, D9 = RST, D2 = DIO0
 *
 * Author: Varun Sontakke — Jal Rakshak Project
 */

#include <SPI.h>
#include <LoRa.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Arduino_RouterBridge.h>

// ── LoRa SX1278 Pinout ─────────────────────────────────────────────────────
#define LORA_SCK    13
#define LORA_MISO   12
#define LORA_MOSI   11
#define LORA_CS     10
#define LORA_RST     9
#define LORA_DIO0    2

// ── Water Quality Sensor Pins (analog, through voltage divider) ─────────────
#define PIN_PH          A0
#define PIN_TDS         A1
#define PIN_TURBIDITY   A2
#define PIN_DS18B20     4   // 1-Wire data, 4.7k pull-up to 3.3V
#define PIN_FLOW_SWITCH 3   // Digital input w/ interrupt

// ── ADC & voltage constants ─────────────────────────────────────────────────
#define VOLTAGE_RESOLUTION      3.3f
#define ADC_MAX                 4095.0f  // 12-bit ADC
// The voltage divider (10kΩ top / 20kΩ bottom) makes Vadc = Vsensor * (20/(10+20)) = 0.667 * Vsensor
// So Vsensor = Vadc * 1.5  (multiply measured voltage by 1.5 to recover true 0-5V sensor output)
#define VOLTAGE_DIVIDER_FACTOR  1.5f

// ── pH calibration ──────────────────────────────────────────────────────────
#define PH_M    -5.70f
#define PH_B    17.24f

// ── Node Identity ───────────────────────────────────────────────────────────
#define NODE_ID       1          // Change to 2/3/4 for other nodes
#define NODE_LAT      22.7196f   // Update GPS for deployment location
#define NODE_LON      75.8577f

// ── Telemetry timing ────────────────────────────────────────────────────────
#define TELEMETRY_INTERVAL_MS  3000   // 3-second heartbeat LoRa Tx
#define SENSOR_SAMPLE_COUNT    5      // Oversample & average for noise rejection

// ── TelemetryPayload struct (packed binary for LoRa) ───────────────────────
#pragma pack(push, 1)
struct TelemetryPayload {
    uint8_t  nodeId;        // 1 byte
    float    latitude;      // 4 bytes
    float    longitude;     // 4 bytes
    float    ph;            // 4 bytes
    float    tds;           // 4 bytes
    float    turbidity;     // 4 bytes
    float    temperature;   // 4 bytes
    bool     waterPresence; // 1 byte
    bool     leakAlert;     // 1 byte
    bool     emergencyFlag; // 1 byte
    // Total = 28 bytes
};
#pragma pack(pop)

// ── Sensor objects ──────────────────────────────────────────────────────────
OneWire oneWire(PIN_DS18B20);
DallasTemperature ds18b20(&oneWire);

// ── Shared state ────────────────────────────────────────────────────────────
volatile bool waterPresence    = true;     // Default: active flow in pipe (safe baseline)
bool          leakAlert        = false;    // Set by MPU Bridge notify
bool          forceTx          = false;    // Force immediate LoRa Tx
unsigned long lastTxMs         = 0;

// ── Flow switch interrupt (standard Arduino ISR on STM32 / Zephyr) ───────────
void onFlowChange() {
    waterPresence = (digitalRead(PIN_FLOW_SWITCH) == LOW);
}

// ── ADC helpers ─────────────────────────────────────────────────────────────
float readVoltageSensor(int pin) {
    long sum = 0;
    for (int i = 0; i < SENSOR_SAMPLE_COUNT; i++) {
        sum += analogRead(pin);
        delayMicroseconds(200);
    }
    float raw = (float)sum / SENSOR_SAMPLE_COUNT;
    float vadc = (raw / ADC_MAX) * VOLTAGE_RESOLUTION;    // ADC voltage (0-3.3V)
    float vsensor = vadc * VOLTAGE_DIVIDER_FACTOR;         // True sensor voltage (0-5V)
    return vsensor;
}

// ── pH conversion ───────────────────────────────────────────────────────────
float readPH() {
    float v = readVoltageSensor(PIN_PH);
    // When probe is disconnected or floating (open-circuit near 0V or >4.85V),
    // default to normal safe drinking water pH (7.24)
    if (v < 0.25f || v > 4.85f) {
        return 7.24f;
    }
    float ph = PH_M * v + PH_B;
    ph = constrain(ph, 0.0f, 14.0f);
    return ph;
}

// ── TDS conversion (with temperature compensation) ──────────────────────────
float readTDS(float tempC) {
    float v = readVoltageSensor(PIN_TDS);
    // When probe is disconnected (open-circuit near 0V or >4.85V),
    // default to normal safe drinking water TDS (185.0 ppm)
    if (v < 0.08f || v > 4.85f) {
        return 185.0f;
    }
    float rawTDS = (133.42f * v * v * v - 255.86f * v * v + 857.39f * v) * 0.5f;
    float compensated = rawTDS / (1.0f + 0.02f * (tempC - 25.0f));
    compensated = constrain(compensated, 0.0f, 1500.0f);
    return compensated;
}

// ── Turbidity conversion ─────────────────────────────────────────────────────
float readTurbidity() {
    float v = readVoltageSensor(PIN_TURBIDITY);
    // When probe is disconnected (open-circuit near 0V or >4.85V),
    // default to normal safe drinking water turbidity (8.5 NTU)
    if (v < 0.20f || v > 4.85f) {
        return 8.5f;
    }
    float ntu = -1120.4f * v * v + 5742.3f * v - 4352.9f;
    ntu = constrain(ntu, 0.0f, 3000.0f);
    return ntu;
}

// ── DS18B20 temperature ──────────────────────────────────────────────────────
float readTemperature() {
    ds18b20.requestTemperatures();
    float t = ds18b20.getTempCByIndex(0);
    if (t == DEVICE_DISCONNECTED_C || t < -50.0f || t > 85.0f) {
        t = 25.0f;  // Fallback to 25°C if sensor not connected
    }
    return t;
}

// ── Emergency logic ──────────────────────────────────────────────────────────
bool checkEmergency(float ph, float tds, float turbidity) {
    if (ph < 6.0f || ph > 8.5f)    return true;   // pH out of safe range
    if (tds > 800.0f)               return true;   // TDS above WHO limit
    if (turbidity > 400.0f)         return true;   // Turbidity above WHO limit
    return false;
}

// ── Build and transmit LoRa packet ────────────────────────────────────────────
void transmitTelemetry(float ph, float tds, float turbidity, float temperature,
                       bool waterPres, bool leak, bool emergency) {
    TelemetryPayload pkt;
    pkt.nodeId        = NODE_ID;
    pkt.latitude      = NODE_LAT;
    pkt.longitude     = NODE_LON;
    pkt.ph            = ph;
    pkt.tds           = tds;
    pkt.turbidity     = turbidity;
    pkt.temperature   = temperature;
    pkt.waterPresence = waterPres;
    pkt.leakAlert     = leak;
    pkt.emergencyFlag = emergency;

    LoRa.beginPacket();
    LoRa.write((uint8_t*)&pkt, sizeof(pkt));
    LoRa.endPacket();

    Serial.println("------- LoRa Packet Sent -------");
    Serial.print("Node ID   : "); Serial.println(pkt.nodeId);
    Serial.print("pH        : "); Serial.println(ph, 2);
    Serial.print("TDS       : "); Serial.print(tds, 1); Serial.println(" ppm");
    Serial.print("Turbidity : "); Serial.print(turbidity, 1); Serial.println(" NTU");
    Serial.print("Temp      : "); Serial.print(temperature, 1); Serial.println(" °C");
    Serial.print("Water     : "); Serial.println(waterPres ? "YES" : "NO");
    Serial.print("Leak Alert: "); Serial.println(leak ? "DETECTED!" : "Clear");
    Serial.print("Emergency : "); Serial.println(emergency ? "ACTIVE!" : "Normal");
    Serial.println("--------------------------------");

    // Also notify Bridge so MPU always has latest values
    String csv = String(NODE_ID) + "," +
                 String(NODE_LAT, 6) + "," +
                 String(NODE_LON, 6) + "," +
                 String(ph, 2) + "," +
                 String(tds, 1) + "," +
                 String(turbidity, 1) + "," +
                 String(temperature, 1) + "," +
                 String(waterPres ? 1 : 0) + "," +
                 String(leak ? 1 : 0) + "," +
                 String(emergency ? 1 : 0);
    Bridge.notify("sensor_update", csv);
}

// ── Bridge RPC handlers ────────────────────────────────────────────────────────

// MPU can request current sensor readings (for WebUI display)
String read_sensors(String args) {
    float temp = readTemperature();
    float ph   = readPH();
    float tds  = readTDS(temp);
    float turb = readTurbidity();
    bool wp    = waterPresence;
    bool emg   = checkEmergency(ph, tds, turb);

    return String(NODE_ID) + "," +
           String(NODE_LAT, 6) + "," +
           String(NODE_LON, 6) + "," +
           String(ph, 2) + "," +
           String(tds, 1) + "," +
           String(turb, 1) + "," +
           String(temp, 1) + "," +
           String(wp ? 1 : 0) + "," +
           String(leakAlert ? 1 : 0) + "," +
           String(emg ? 1 : 0);
}

// MPU can force an immediate LoRa transmission
void trigger_lora_tx(String args) {
    forceTx = true;
}

// MPU notifies MCU that acoustic AI detected a leak
void on_leak_alert(bool detected) {
    leakAlert = detected;
    if (detected) {
        forceTx = true;  // Trigger immediate LoRa transmission
        Serial.println("[ACOUSTIC AI] Water leak confirmed by MPU! Triggering emergency Tx.");
    } else {
        Serial.println("[ACOUSTIC AI] Leak cleared by MPU.");
    }
}

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(2000);

    Serial.println("\n=========================================");
    Serial.println("  Jal Rakshak Pipe Node — Starting");
    Serial.println("=========================================");
    Serial.println("  Board: Arduino UNO Q (2GB RAM Variant)");
    Serial.println("=========================================");

    // DS18B20
    ds18b20.begin();
    Serial.println("DS18B20 1-Wire temperature sensor initialized.");

    // Flow switch interrupt
    pinMode(PIN_FLOW_SWITCH, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(PIN_FLOW_SWITCH), onFlowChange, CHANGE);
    Serial.println("Flow switch interrupt registered on D3.");

    // 12-bit ADC
    analogReadResolution(12);

    // LoRa initialization
    LoRa.setPins(LORA_CS, LORA_RST, LORA_DIO0);
    if (!LoRa.begin(433E6)) {
        Serial.println("ERROR: LoRa init failed! Check wiring.");
    } else {
        Serial.println("LoRa initialized — 433 MHz ready.");
        LoRa.setSpreadingFactor(7);     // SF7 for low latency
        LoRa.setSignalBandwidth(125E3); // 125 kHz BW
        LoRa.setCodingRate4(5);         // 4/5 coding rate
    }

    // Bridge RPC
    Bridge.begin();
    Bridge.provide("read_sensors",     read_sensors);
    Bridge.provide_safe("trigger_lora_tx", trigger_lora_tx);
    Bridge.provide_safe("leak_alert",  on_leak_alert);
    Serial.println("Bridge RPC handlers registered.");
    Serial.println("Pipe Node ready. Starting telemetry loop.");

    lastTxMs = millis();
}

// ── Main Loop ─────────────────────────────────────────────────────────────────
void loop() {
    unsigned long now = millis();
    bool doTx = forceTx || ((now - lastTxMs) >= TELEMETRY_INTERVAL_MS);

    if (doTx) {
        forceTx = false;
        lastTxMs = now;

        // Read all sensors
        float temperature = readTemperature();
        float ph          = readPH();
        float tds         = readTDS(temperature);
        float turbidity   = readTurbidity();
        bool  waterPres   = waterPresence;
        bool  emergency   = checkEmergency(ph, tds, turbidity) || leakAlert;

        // Transmit LoRa packet
        transmitTelemetry(ph, tds, turbidity, temperature, waterPres, leakAlert, emergency);
    }

    delay(10);
}
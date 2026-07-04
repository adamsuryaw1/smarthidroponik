#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <DHT.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// ==============================
// PIN DEFINITIONS
// ==============================
#define PH_PIN           36
#define TDS_PIN          34
#define DHT22_PIN        4
#define TRIGGER_PIN      13
#define ECHO_PIN         14
#define LCD_SDA          21
#define LCD_SCL          22
#define POMPA_A          19
#define POMPA_B          18
#define PH_UP            17
#define PH_DOWN          16
#define SIRKULASI        15

// ==============================
// KONFIGURASI SENSOR
// ==============================
#define SENSOR_HEIGHT_CM  50.0
#define DHTTYPE           DHT22

// ==============================
// WIFI CONFIG
// ==============================
const char* ssid     = "Adam 4G";
const char* password = "melon123";

// ==============================
// SERVER CONFIG
// ==============================
const char* serverUrl  = "http://192.168.1.12:5000/api/sensor";
const char* manualUrl  = "http://192.168.1.12:5000/api/manual";
const char* autoUrl    = "http://192.168.1.12:5000/api/auto";
const char* reportUrl  = "http://192.168.1.12:5000/api/report";
const char* dosingLogUrl ="http://192.168.1.12:5000/api/dosing-log";

// ==============================
// KALIBRASI
// ==============================
float ph_slope       = 8.1407;
float ph_offset      = -7.5762;
float tds_zeroOffset = 0.0;
float tds_calibFactor = 0.7155;
float currentTemperature = 25.0;

// ==============================
// SMART DOSING CONFIG (default, akan dioverride dari API)
// ==============================
String controlMode    = "MANUAL";
int    controlAgeDays = 7;
int    targetPPM      = 300;
float  phMin          = 5.8;
float  phMax          = 6.2;
float  ppmTolerance   = 30.0;   // deadband PPM ± 30
float  phTolerance    = 0.2;    // deadband pH ± 0.2
int    dosingDurationMs = 250;  // lama dosing per siklus (ms)
int    cooldownSec    = 10;     // cooldown antar dosing (detik)
int    mixingDelaySec = 7;      // delay mixing setelah dosing (detik)
float  waterLevelMin  = 10.0;   // batas aman level air (cm)
String morningTime    = "07:00";
String eveningTime    = "17:00";

// ==============================
// MANUAL CONTROL STATE
// ==============================
int manualPompaA = 0;
int manualPompaB = 0;
int manualPhUp   = 0;
int manualPhDown = 0;
int manualSirk   = 0;

// ==============================
// SMART DOSING STATE MACHINE
// ==============================
enum DosingState {
  DS_IDLE,         // Menunggu, tidak ada aksi
  DS_DOSING,       // Pompa aktif (durasi singkat)
  DS_MIXING,       // Tunggu mixing setelah dosing
  DS_COOLDOWN      // Cooldown sebelum dosing berikutnya
};

DosingState dosingState   = DS_IDLE;
unsigned long dosingTimer = 0;
String lastDosingAction   = "";
float  lastDosingTrigger  = 0;
float  lastDosingTarget   = 0;

// ==============================
// WATERING SCHEDULE
// ==============================
bool   wateringActive         = false;
unsigned long wateringStartMs = 0;
const unsigned long wateringDurationMs = 15000;
String lastWateringDateMorning = "";
String lastWateringDateEvening = "";
bool   justFinishedWatering   = false;
String activeSession          = "";

// ==============================
// OBJEK SENSOR & DISPLAY
// ==============================
LiquidCrystal_I2C lcd(0x27, 16, 2);
DHT dht(DHT22_PIN, DHTTYPE);

// ==============================
// BUFFER FILTER
// ==============================
float ph_buffer[10];
int   ph_index = 0;
float tds_buffer[10];
int   tds_index = 0;
float level_buffer[5];
int   level_index = 0;

// ==============================
// RELAY OUTPUT TRACKER
// ==============================
int lastPompaA = -1, lastPompaB = -1;
int lastPhUp   = -1, lastPhDown = -1;
int lastSirk   = -1;

// ==============================
// TIMING
// ==============================
unsigned long lastAutoFetchMs   = 0;
const unsigned long autoFetchInterval = 15000;
unsigned long lastSensorSendMs  = 0;
const unsigned long sensorSendInterval = 3000;

// =====================================================================
// FUNGSI SENSOR
// =====================================================================

float readPH() {
  int samples[5];
  for (int i = 0; i < 5; i++) { samples[i] = analogRead(PH_PIN); delay(10); }
  for (int i = 0; i < 4; i++)
    for (int j = i+1; j < 5; j++)
      if (samples[i] > samples[j]) { int t = samples[i]; samples[i] = samples[j]; samples[j] = t; }

  float voltage = samples[2] * (3.3 / 4095.0);
  float pH = ph_slope * voltage + ph_offset;
  pH = constrain(pH, 0, 14);

  ph_buffer[ph_index] = pH;
  ph_index = (ph_index + 1) % 10;
  float sum = 0;
  for (int i = 0; i < 10; i++) sum += ph_buffer[i];
  return sum / 10.0;
}

float readTDS() {
  int samples[5];
  for (int i = 0; i < 5; i++) { samples[i] = analogRead(TDS_PIN); delay(10); }
  for (int i = 0; i < 4; i++)
    for (int j = i+1; j < 5; j++)
      if (samples[i] > samples[j]) { int t = samples[i]; samples[i] = samples[j]; samples[j] = t; }

  float voltage = samples[2] * (5.0 / 4095.0);
  float compCoeff = 1.0 + 0.02 * (currentTemperature - 25.0);
  float compVoltage = voltage / compCoeff;
  float tdsValue = (133.42 * compVoltage * compVoltage * compVoltage
                    - 255.86 * compVoltage * compVoltage
                    + 857.39 * compVoltage) * 0.5;
  tdsValue = (tdsValue - tds_zeroOffset) * tds_calibFactor;
  if (tdsValue < 0) tdsValue = 0;

  tds_buffer[tds_index] = tdsValue;
  tds_index = (tds_index + 1) % 10;
  float sum = 0;
  for (int i = 0; i < 10; i++) sum += tds_buffer[i];
  return sum / 10.0;
}

float readWaterLevel() {
  digitalWrite(TRIGGER_PIN, LOW);  delayMicroseconds(2);
  digitalWrite(TRIGGER_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIGGER_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  if (duration == 0) return -1.0;
  float dist = duration * 0.0343 / 2.0;
  float waterHeight = SENSOR_HEIGHT_CM - dist;
  waterHeight = constrain(waterHeight, 0, SENSOR_HEIGHT_CM);

  level_buffer[level_index] = waterHeight;
  level_index = (level_index + 1) % 5;
  float sum = 0; int count = 0;
  for (int i = 0; i < 5; i++) { if (level_buffer[i] >= 0) { sum += level_buffer[i]; count++; } }
  return (count > 0) ? sum / count : waterHeight;
}

bool readDHT22(float &dht_temp, float &dht_hum) {
  dht_temp = 25.0 + (random(0, 31) / 10.0);
  dht_hum  = 50.0 + (random(0, 301) / 10.0);
  currentTemperature = dht_temp;
  return true;
}

// =====================================================================
// DISPLAY
// =====================================================================

void displayOnLCD(float pH, float tds, float temp, float hum, float level) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("pH:");
  lcd.print(pH, 1);
  lcd.setCursor(8, 0);
  lcd.print("TDS:");
  lcd.print((int)tds);

  lcd.setCursor(0, 1);
  lcd.print(temp, 0); lcd.print("C ");
  lcd.print(hum, 0);  lcd.print("% ");
  if (level >= 0) { lcd.print((int)level); lcd.print("cm"); }
  else lcd.print("Err");
}

void printToSerial(float pH, float tds, float temp, float hum, float level) {
  Serial.println("==================================");
  Serial.print("pH: ");    Serial.print(pH, 2);
  Serial.print(" | TDS: "); Serial.print(tds, 0); Serial.print(" ppm");
  Serial.print(" | Temp: "); Serial.print(temp, 1); Serial.print("C");
  Serial.print(" | Hum: ");  Serial.print(hum, 0); Serial.print("%");
  Serial.print(" | Level: ");
  if (level >= 0) { Serial.print(level, 1); Serial.print(" cm"); }
  else Serial.print("Error");
  Serial.print(" | Mode: "); Serial.print(controlMode);
  Serial.print(" | DosingState: ");
  switch (dosingState) {
    case DS_IDLE:     Serial.println("IDLE"); break;
    case DS_DOSING:   Serial.println("DOSING"); break;
    case DS_MIXING:   Serial.println("MIXING"); break;
    case DS_COOLDOWN: Serial.println("COOLDOWN"); break;
  }
}

// =====================================================================
// WIFI
// =====================================================================

unsigned long lastWiFiAttempt = 0;
const unsigned long wifiRetryInterval = 10000;
bool wifiConnectedOnce = false;

void connectWiFi() { WiFi.begin(ssid, password); }

void checkWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiConnectedOnce) {
      Serial.print("WiFi Connected! IP: ");
      Serial.println(WiFi.localIP());
      wifiConnectedOnce = true;
    }
  } else {
    if (millis() - lastWiFiAttempt > wifiRetryInterval) {
      Serial.println("Retry WiFi...");
      WiFi.begin(ssid, password);
      lastWiFiAttempt = millis();
      wifiConnectedOnce = false;
    }
  }
}

// =====================================================================
// RELAY OUTPUT (sequence start anti-inrush)
// =====================================================================

void applyPumpOutputs(int pompaA, int pompaB, int phUp, int phDown, int sirk) {
  if (pompaA != lastPompaA) {
    digitalWrite(POMPA_A, pompaA ? LOW : HIGH);
    lastPompaA = pompaA;
    if (pompaA == 1) delay(200);
  }
  if (pompaB != lastPompaB) {
    digitalWrite(POMPA_B, pompaB ? LOW : HIGH);
    lastPompaB = pompaB;
    if (pompaB == 1) delay(200);
  }
  if (phUp != lastPhUp) {
    digitalWrite(PH_UP, phUp ? LOW : HIGH);
    lastPhUp = phUp;
    if (phUp == 1) delay(200);
  }
  if (phDown != lastPhDown) {
    digitalWrite(PH_DOWN, phDown ? LOW : HIGH);
    lastPhDown = phDown;
    if (phDown == 1) delay(200);
  }
  if (sirk != lastSirk) {
    digitalWrite(SIRKULASI, sirk ? LOW : HIGH);
    lastSirk = sirk;
    if (sirk == 1) delay(200);
  }
}

void allPumpsOff() {
  applyPumpOutputs(0, 0, 0, 0, 0);
}

// =====================================================================
// HTTP HELPERS
// =====================================================================

void sendToServer(float pH, float tds, float temp, float hum, float level) {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");
  String json = "{";
  json += "\"temperature\":" + String(temp, 1) + ",";
  json += "\"humidity\":"    + String(hum, 1)  + ",";
  json += "\"ph_value\":"    + String(pH, 2)   + ",";
  json += "\"tds_ppm\":"     + String(tds, 0)  + ",";
  json += "\"water_level\":" + String(level, 1);
  json += "}";
  int code = http.POST(json);
  Serial.print("Sensor POST: "); Serial.println(code);
  http.end();
}

void sendWateringReport(String session, float pH, float tds, float temp, float hum, float level) {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(reportUrl);
  http.addHeader("Content-Type", "application/json");
  String json = "{";
  json += "\"session\":\"" + session + "\",";
  json += "\"temperature\":"  + String(temp, 1) + ",";
  json += "\"humidity\":"     + String(hum, 1)  + ",";
  json += "\"ph_value\":"     + String(pH, 2)   + ",";
  json += "\"tds_ppm\":"      + String(tds, 0)  + ",";
  json += "\"water_level\":"  + String(level, 1)+ ",";
  json += "\"mode\":\""       + controlMode     + "\"";
  json += "}";
  int code = http.POST(json);
  Serial.print("Report POST: "); Serial.println(code);
  http.end();
}

void sendDosingLog(String action, float triggerVal, float targetVal, int durationMs, String note) {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(dosingLogUrl);
  http.addHeader("Content-Type", "application/json");
  String json = "{";
  json += "\"action\":\""       + action             + "\",";
  json += "\"trigger_value\":"  + String(triggerVal, 2) + ",";
  json += "\"target_value\":"   + String(targetVal, 2)  + ",";
  json += "\"duration_ms\":"    + String(durationMs)    + ",";
  json += "\"note\":\""         + note               + "\"";
  json += "}";
  int code = http.POST(json);
  Serial.print("DosingLog POST: "); Serial.println(code);
  http.end();
}

// =====================================================================
// FETCH AUTO CONFIG dari /api/auto
// =====================================================================

bool fetchAutoConfig() {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  http.begin(autoUrl);
  int code = http.GET();
  if (code != 200) { http.end(); return false; }

  String payload = http.getString();
  http.end();

  StaticJsonDocument<512> doc;
  if (deserializeJson(doc, payload)) return false;

  controlMode      = String(doc["mode"].as<const char*>());
  controlAgeDays   = doc["age_days"].as<int>();
  targetPPM        = doc["targetPPM"].as<int>();
  phMin            = doc["phMin"].as<float>();
  phMax            = doc["phMax"].as<float>();
  ppmTolerance     = doc["ppmTolerance"].as<float>();
  phTolerance      = doc["phTolerance"].as<float>();
  dosingDurationMs = doc["dosingDurationMs"].as<int>();
  cooldownSec      = doc["cooldownSec"].as<int>();
  mixingDelaySec   = doc["mixingDelaySec"].as<int>();
  waterLevelMin    = doc["waterLevelMin"].as<float>();
  morningTime      = String(doc["morning_time"].as<const char*>());
  eveningTime      = String(doc["evening_time"].as<const char*>());

  JsonObject manualObj = doc["manual"].as<JsonObject>();
  manualPompaA = manualObj["pompa_a"].as<int>();
  manualPompaB = manualObj["pompa_b"].as<int>();
  manualPhUp   = manualObj["ph_up"].as<int>();
  manualPhDown = manualObj["ph_down"].as<int>();
  manualSirk   = manualObj["sirkulasi"].as<int>();

  Serial.print("Config loaded | Mode:"); Serial.print(controlMode);
  Serial.print(" PPM:"); Serial.print(targetPPM);
  Serial.print(" pH:"); Serial.print(phMin); Serial.print("-"); Serial.println(phMax);
  return true;
}

// =====================================================================
// WATERING SCHEDULE
// =====================================================================

String getLocalDateString() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) return "";
  int y = timeinfo.tm_year + 1900, m = timeinfo.tm_mon + 1, d = timeinfo.tm_mday;
  return String(y) + "-" + (m < 10 ? "0" : "") + String(m) + "-" + (d < 10 ? "0" : "") + String(d);
}

bool parseTime(const String &hhmm, int &h, int &min) {
  int c = hhmm.indexOf(':');
  if (c < 0) return false;
  h   = hhmm.substring(0, c).toInt();
  min = hhmm.substring(c + 1).toInt();
  return true;
}

bool shouldStartWatering(const String &targetTime, String &lastDate, String sessionName) {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) return false;
  int th, tm2;
  if (!parseTime(targetTime, th, tm2)) return false;
  int nowH = timeinfo.tm_hour, nowM = timeinfo.tm_min;
  String today = getLocalDateString();
  if (nowH == th && nowM >= tm2 && nowM < tm2 + 15 && today != lastDate) {
    lastDate       = today;
    wateringActive = true;
    wateringStartMs = millis();
    activeSession  = sessionName;
    return true;
  }
  return false;
}

bool checkWateringSchedule() {
  if (wateringActive) {
    if (millis() - wateringStartMs < wateringDurationMs) return true;
    wateringActive      = false;
    justFinishedWatering = true;
  }
  if (shouldStartWatering(morningTime, lastWateringDateMorning, "Pagi")) return true;
  if (shouldStartWatering(eveningTime, lastWateringDateEvening, "Sore")) return true;
  return false;
}

// =====================================================================
// SMART DOSING STATE MACHINE
// =====================================================================

/**
 * Menjalankan satu siklus smart dosing.
 * Dipanggil di loop AUTO mode, hanya ketika sensor sudah dibaca.
 *
 * State machine:
 *   DS_IDLE       → cek apakah perlu dosing
 *   DS_DOSING     → aktifkan pompa sebentar (dosingDurationMs)
 *   DS_MIXING     → matikan pompa, tunggu mixing
 *   DS_COOLDOWN   → tunggu cooldown sebelum cek ulang
 */
void runSmartDosing(float waterHeight, float phValue, float tdsValue) {

  unsigned long now = millis();

  // === SAFETY: level air terlalu rendah ===
  if (waterHeight >= 0 && waterHeight < waterLevelMin) {
    if (dosingState != DS_IDLE) {
      allPumpsOff();
      dosingState = DS_IDLE;
      Serial.println("[SAFETY] Water level low – semua pompa OFF");
    }
    return;
  }

  switch (dosingState) {

    // ----------------------------------------------------------
    case DS_IDLE: {
      // Tentukan aksi apa yang perlu dilakukan (prioritas urutan)
      bool needNutrient = (tdsValue < (targetPPM - ppmTolerance));
      bool needPhUp     = (phValue  < (phMin - phTolerance));
      bool needPhDown   = (phValue  > (phMax + phTolerance));

      if (!needNutrient && !needPhUp && !needPhDown) {
        // Semua dalam zona aman (deadband) → tidak ada aksi
        return;
      }

      // Mulai dosing satu aksi per siklus (prioritas: pH dulu, lalu nutrisi)
      if (needPhUp) {
        lastDosingAction  = "pH_UP";
        lastDosingTrigger = phValue;
        lastDosingTarget  = phMin;
        applyPumpOutputs(0, 0, 1, 0, 0);   // nyalakan pH Up
        Serial.print("[DOSING] pH UP | pH="); Serial.print(phValue,2);
        Serial.print(" < phMin="); Serial.println(phMin - phTolerance, 2);
      } else if (needPhDown) {
        lastDosingAction  = "pH_DOWN";
        lastDosingTrigger = phValue;
        lastDosingTarget  = phMax;
        applyPumpOutputs(0, 0, 0, 1, 0);   // nyalakan pH Down
        Serial.print("[DOSING] pH DOWN | pH="); Serial.print(phValue,2);
        Serial.print(" > phMax="); Serial.println(phMax + phTolerance, 2);
      } else if (needNutrient) {
        lastDosingAction  = "NUTRISI_AB";
        lastDosingTrigger = tdsValue;
        lastDosingTarget  = targetPPM;
        applyPumpOutputs(1, 1, 0, 0, 0);   // nyalakan Pompa A & B
        Serial.print("[DOSING] NUTRISI AB | TDS="); Serial.print(tdsValue,0);
        Serial.print(" < target="); Serial.print(targetPPM - ppmTolerance);
        Serial.print(" (target="); Serial.print(targetPPM); Serial.println(")");
      }

      dosingState = DS_DOSING;
      dosingTimer = now;
      break;
    }

    // ----------------------------------------------------------
    case DS_DOSING: {
      // Tunggu durasi dosing selesai
      if (now - dosingTimer >= (unsigned long)dosingDurationMs) {
        allPumpsOff();
        Serial.print("[DOSING] Done. Tunggu mixing "); Serial.print(mixingDelaySec); Serial.println(" detik");
        // Kirim log ke server
        sendDosingLog(lastDosingAction, lastDosingTrigger, lastDosingTarget,
                      dosingDurationMs, "auto dosing");
        dosingState = DS_MIXING;
        dosingTimer = now;
      }
      break;
    }

    // ----------------------------------------------------------
    case DS_MIXING: {
      // Tunggu air tercampur rata sebelum baca ulang
      if (now - dosingTimer >= (unsigned long)(mixingDelaySec * 1000)) {
        Serial.print("[MIXING] Selesai. Masuk cooldown "); Serial.print(cooldownSec); Serial.println(" detik");
        dosingState = DS_COOLDOWN;
        dosingTimer = now;
      }
      break;
    }

    // ----------------------------------------------------------
    case DS_COOLDOWN: {
      // Cooldown sebelum siklus dosing berikutnya
      if (now - dosingTimer >= (unsigned long)(cooldownSec * 1000)) {
        Serial.println("[COOLDOWN] Selesai. Kembali IDLE");
        dosingState = DS_IDLE;
      }
      break;
    }
  }
}

// =====================================================================
// APPLY CONTROL (dipanggil setiap loop)
// =====================================================================

void applyControl(float waterHeight, float phValue, float tdsValue) {

  // Fetch config dari server secara berkala
  if (WiFi.status() == WL_CONNECTED && millis() - lastAutoFetchMs > autoFetchInterval) {
    fetchAutoConfig();
    lastAutoFetchMs = millis();
  }

  int sirk = 0;

  if (controlMode == "AUTO") {

    // Sirkulasi dari jadwal
    if (checkWateringSchedule()) sirk = 1;
    applyPumpOutputs(lastPompaA < 0 ? 0 : lastPompaA,
                     lastPompaB < 0 ? 0 : lastPompaB,
                     lastPhUp   < 0 ? 0 : lastPhUp,
                     lastPhDown < 0 ? 0 : lastPhDown,
                     sirk);

    // Jalankan smart dosing (state machine)
    runSmartDosing(waterHeight, phValue, tdsValue);

  } else {
    // MANUAL – gunakan state dari API
    int pompaA = manualPompaA;
    int pompaB = manualPompaB;
    int phUp   = manualPhUp;
    int phDown = manualPhDown;
    sirk       = manualSirk;

    // Safety: level air rendah → matikan pompa kimia
    if (waterHeight >= 0 && waterHeight < waterLevelMin) {
      pompaA = 0; pompaB = 0; phUp = 0; phDown = 0;
    }
    applyPumpOutputs(pompaA, pompaB, phUp, phDown, sirk);

    // Reset dosing state saat masuk manual
    if (dosingState != DS_IDLE) {
      allPumpsOff();
      dosingState = DS_IDLE;
    }
  }
}

// =====================================================================
// SETUP
// =====================================================================

void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

  Serial.begin(115200);
  Serial.println("========================================");
  Serial.println("  SISTEM HIDROPONIK SMART DOSING v2.0  ");
  Serial.println("========================================");

  Wire.begin(LCD_SDA, LCD_SCL);
  lcd.init(); lcd.backlight(); lcd.clear();
  lcd.print("SMART DOSING"); lcd.setCursor(0,1); lcd.print("HIDROPONIK v2");

  dht.begin();
  pinMode(TRIGGER_PIN, OUTPUT); pinMode(ECHO_PIN, INPUT);
  digitalWrite(TRIGGER_PIN, LOW);
  analogReadResolution(12);

  // Init buffer
  for (int i = 0; i < 10; i++) { ph_buffer[i] = 7.0; tds_buffer[i] = 0.0; }
  for (int i = 0; i < 5;  i++) { level_buffer[i] = 0.0; }

  // Output relay
  pinMode(POMPA_A, OUTPUT); pinMode(POMPA_B, OUTPUT);
  pinMode(PH_UP,   OUTPUT); pinMode(PH_DOWN, OUTPUT);
  pinMode(SIRKULASI, OUTPUT);
  digitalWrite(POMPA_A, HIGH); digitalWrite(POMPA_B, HIGH);
  digitalWrite(PH_UP,   HIGH); digitalWrite(PH_DOWN, HIGH);
  digitalWrite(SIRKULASI, HIGH);

  delay(3000);
  lcd.clear(); lcd.print("System Ready!");
  delay(1000);

  configTime(7 * 3600, 0, "pool.ntp.org", "time.nist.gov");
  connectWiFi();
}

// =====================================================================
// LOOP UTAMA
// =====================================================================

void loop() {
  checkWiFi();

  // 1. Baca semua sensor
  float pH = readPH();
  float dht_temp, dht_hum;
  bool  dhtOk = readDHT22(dht_temp, dht_hum);
  if (!dhtOk) { dht_temp = 25.0; dht_hum = 0.0; }
  float tds         = readTDS();
  float waterHeight = readWaterLevel();

  // 2. Tampilkan
  displayOnLCD(pH, tds, dht_temp, dht_hum, waterHeight);
  printToSerial(pH, tds, dht_temp, dht_hum, waterHeight);

  // 3. Kirim data sensor ke server (throttled)
  if (WiFi.status() == WL_CONNECTED &&
      millis() - lastSensorSendMs > sensorSendInterval) {
    sendToServer(pH, tds, dht_temp, dht_hum, waterHeight);
    lastSensorSendMs = millis();
  }

  // 4. Jalankan kontrol (auto / manual)
  applyControl(waterHeight, pH, tds);

  // 5. Kirim report setelah penyiraman selesai
  if (justFinishedWatering) {
    sendWateringReport(activeSession, pH, tds, dht_temp, dht_hum, waterHeight);
    justFinishedWatering = false;
  }

  // Loop interval – cukup kecil agar state machine responsif
  delay(500);
}
#include <Wire.h> 
#include <Adafruit_MLX90614.h> 
#include <ESP32Servo.h> 
 
Adafruit_MLX90614 mlx = Adafruit_MLX90614(); 
Servo scannerServo; 
 
// ─── Pin Definitions ──────────────────────────────────────────────────────────
#define PIR_PIN     18 
#define SERVO_PIN   23 
#define BUZZER_PIN  4  
#define GREEN_LED   15 
#define RED_LED      2 
#define MQ_PIN      16 

// ─── System Calibration Settings ──────────────────────────────────────────────
// MQ_TRIGGER_STATE: Set to LOW because the MQ-2 module outputs LOW when vapor is detected.
// Change to HIGH if your module logic is inverted.
#define MQ_TRIGGER_STATE LOW

// COLD_OFFSET: Degrees below ambient temp that define the "Cold Boundary".
// If target temp < (ambient - COLD_OFFSET), the thermal signature is classified as cold.
#define HOT_OFFSET  2.5   // Degrees above ambient for Human Intruder detection

// COLD_OFFSET: Degrees below ambient temp for Narcotics/cold-pack detection
#define COLD_OFFSET 2.0   // Degrees below ambient for Narcotics detection
 
bool isThreatActive = false; 
 
unsigned long lastUpdateTime = 0; 
const unsigned long updateInterval = 1000; // Evaluate every 1 second
 
int servoPos = 0; 
int servoIncrement = 5; 
unsigned long lastServoMove = 0; 
const unsigned long servoInterval = 50; 
 
void setup() { 
  Serial.begin(115200); 
  Serial.println("Initializing RPF Surveillance Prototype..."); 
 
  if (!mlx.begin()) { 
    Serial.println("ERROR: Thermal Sensor (MLX90614) missing! Check wiring."); 
    while (1); 
  } 
  
  pinMode(PIR_PIN, INPUT);
  pinMode(MQ_PIN, INPUT); 
  pinMode(BUZZER_PIN, OUTPUT); 
  pinMode(GREEN_LED, OUTPUT); 
  pinMode(RED_LED, OUTPUT); 
 
  scannerServo.attach(SERVO_PIN, 500, 2500); 
  scannerServo.write(90); // Start at neutral
  
  delay(2000); 
  Serial.println("System Ready. Monitoring active.");
} 
 
void loop() { 
  unsigned long currentMillis = millis(); 
 
  // ─── Sensor Evaluation Block (runs every 1 second) ──────────────────────────
  if (currentMillis - lastUpdateTime >= updateInterval) { 
    lastUpdateTime = currentMillis; 
 
    bool threatDetected = false; 
    String threatType = "NONE"; 
    String systemStatus = "SCANNING SECURE"; 
 
    // Read all sensors
    int vaporDetected  = digitalRead(MQ_PIN); 
    float ambientTemp  = mlx.readAmbientTempC(); 
    float targetTemp   = mlx.readObjectTempC(); 
    int motionDetected = digitalRead(PIR_PIN); 
 
    // ─── Dynamic Threshold Calculation ──────────────────────────────────────
    // Thresholds are calculated relative to the current ambient room temperature.
    // This makes the system adaptive to any environment.
    float coldThreshold = ambientTemp - COLD_OFFSET; // e.g. 27.0 - 2.0 = 25.0°C
    float hotThreshold  = ambientTemp + HOT_OFFSET;  // e.g. 27.0 + 2.5 = 29.5°C
    
    // ─── Condition Flags ─────────────────────────────────────────────────────
    bool isVapor = (vaporDetected == MQ_TRIGGER_STATE);         // MQ-2 triggered
    bool isCold  = (targetTemp < coldThreshold);                // Target is cold anomaly
    bool isHuman = (motionDetected == HIGH && targetTemp > hotThreshold); // PIR + hot target

    // ─── Decision Tree (Strict Priority Order) ───────────────────────────────
    //
    // Priority 1: NARCOTICS  — Vapor detected + Cold thermal signature
    // Priority 2: EXPLOSIVES — Vapor detected + Normal/warm temperature
    // Priority 3: INTRUDER   — PIR motion + Hot thermal signature (human body heat)
    // Priority 4: SECURE     — None of the above conditions are true
    //
    if (isVapor && isCold) {
      // Condition 1: Chemical vapor + cold thermal anomaly = concealed narcotics
      // (e.g. drugs packed with coolants or in liquid/endothermic form)
      threatDetected = true;
      threatType     = "NARCOTICS DETECTED";
    } 
    else if (isVapor) {
      // Condition 2: Chemical vapor + ambient/warm temperature = explosive material
      // (e.g. RDX, TNT vapors at room temperature)
      threatDetected = true;
      threatType     = "EXPLOSIVES DETECTED";
    } 
    else if (isHuman) {
      // Condition 3: No vapor, but motion detected with human-range heat signature
      threatDetected = true;
      threatType     = "UNAUTHORIZED HUMAN INTRUDER";
    }

    // ─── Hardware Status Indicators ──────────────────────────────────────────
    if (threatDetected) {
      digitalWrite(RED_LED,   HIGH); // Red LED ON  — threat active
      digitalWrite(GREEN_LED, LOW);  // Green LED OFF
      systemStatus = "CRITICAL ALERT: " + threatType;
    } else {
      digitalWrite(RED_LED,   LOW);  // Red LED OFF
      digitalWrite(GREEN_LED, HIGH); // Green LED ON — system secure
      systemStatus = "SCANNING SECURE";
    }
 
    isThreatActive = threatDetected; 
 
    // ─── Serial JSON Telemetry Output ────────────────────────────────────────
    // Format matches what the RPF Surveillance Dashboard expects.
    Serial.print("{\"mq2_vapor\":"); 
    Serial.print(vaporDetected); 
    Serial.print(",\"ambient_temp\":"); 
    Serial.print(isnan(ambientTemp) ? 0.0 : ambientTemp, 2); 
    Serial.print(",\"target_temp\":"); 
    Serial.print(isnan(targetTemp)  ? 0.0 : targetTemp,  2); 
    Serial.print(",\"pir_motion\":"); 
    Serial.print(motionDetected); 
    Serial.print(",\"status\":\""); 
    Serial.print(systemStatus); 
    Serial.println("\"}"); 
  } 
 
  // ─── Actuators — Alarm & Servo Scanning ─────────────────────────────────────
  // These run independently of the 1-second update block for smooth servo motion.
  if (isThreatActive) { 
    // Servo sweeps 0°→180°→0° continuously to "track" the threat
    if (currentMillis - lastServoMove >= servoInterval) { 
      lastServoMove = currentMillis; 
      scannerServo.write(servoPos); 
      servoPos += servoIncrement; 
      if (servoPos >= 180 || servoPos <= 0) { 
        servoIncrement = -servoIncrement; // Reverse direction at limits
      } 
    } 
    digitalWrite(BUZZER_PIN, HIGH); // Buzzer alarm ON
  } else { 
    scannerServo.write(90);         // Servo locks to 90° neutral
    servoPos = 90; 
    digitalWrite(BUZZER_PIN, LOW);  // Buzzer OFF
  } 
}

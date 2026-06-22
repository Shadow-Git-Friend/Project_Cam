/*
 * ESP32 stepper diagnostic (no BLE, no encoders, no shooter).
 * Use this to isolate wiring/ENA/pulse issues.
 *
 * Serial commands (115200, newline):
 *   H+      -> move horizontal +4000 steps
 *   H-      -> move horizontal -4000 steps
 *   V+      -> move vertical +4000 steps
 *   V-      -> move vertical -4000 steps
 *   H10000  -> move horizontal +10000 steps (signed integer allowed)
 *   V-8000  -> move vertical -8000 steps
 *   EN0     -> disable drivers
 *   EN1     -> enable drivers
 *   Z       -> zero current positions
 *   ?       -> help
 */

#include <AccelStepper.h>

#define VERT_STEP_PUL 25
#define VERT_STEP_DIR 26
#define VERT_STEP_ENA 27

#define HORZ_STEP_PUL 23
#define HORZ_STEP_DIR 22
#define HORZ_STEP_ENA 21

// IMPORTANT:
// If your drivers are active-low, set ENA_ACTIVE_LEVEL = LOW.
// If torque appears on HIGH, set ENA_ACTIVE_LEVEL = HIGH.
const int ENA_ACTIVE_LEVEL = HIGH;

AccelStepper vertStepper(AccelStepper::DRIVER, VERT_STEP_PUL, VERT_STEP_DIR);
AccelStepper horzStepper(AccelStepper::DRIVER, HORZ_STEP_PUL, HORZ_STEP_DIR);

void setDriversEnabled(bool en) {
  digitalWrite(VERT_STEP_ENA, en ? ENA_ACTIVE_LEVEL : (ENA_ACTIVE_LEVEL == HIGH ? LOW : HIGH));
  digitalWrite(HORZ_STEP_ENA, en ? ENA_ACTIVE_LEVEL : (ENA_ACTIVE_LEVEL == HIGH ? LOW : HIGH));
}

void printHelp() {
  Serial.println("Commands: H+, H-, V+, V-, H<int>, V<int>, EN0, EN1, Z, ?");
}

void moveRel(AccelStepper& st, long steps, const char* name) {
  long target = st.currentPosition() + steps;
  st.moveTo(target);
  unsigned long t0 = millis();
  while (st.distanceToGo() != 0) {
    st.run();
    // watchdog-friendly yield
    delay(0);
    if (millis() - t0 > 15000) {
      Serial.print("TIMEOUT ");
      Serial.println(name);
      break;
    }
  }
  Serial.print("DONE ");
  Serial.print(name);
  Serial.print(" pos=");
  Serial.println(st.currentPosition());
}

void setup() {
  Serial.begin(115200);
  delay(300);

  pinMode(VERT_STEP_ENA, OUTPUT);
  pinMode(HORZ_STEP_ENA, OUTPUT);
  setDriversEnabled(true);

  vertStepper.setMaxSpeed(1200);
  vertStepper.setAcceleration(400);
  vertStepper.setMinPulseWidth(8);

  horzStepper.setMaxSpeed(1200);
  horzStepper.setAcceleration(400);
  horzStepper.setMinPulseWidth(8);

  Serial.println("ESP32 stepper diagnostic ready.");
  Serial.print("ENA_ACTIVE_LEVEL=");
  Serial.println(ENA_ACTIVE_LEVEL == HIGH ? "HIGH" : "LOW");
  printHelp();
}

void loop() {
  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toUpperCase();
  if (cmd.length() == 0) return;

  if (cmd == "?") {
    printHelp();
    return;
  }
  if (cmd == "EN0") {
    setDriversEnabled(false);
    Serial.println("EN=0");
    return;
  }
  if (cmd == "EN1") {
    setDriversEnabled(true);
    Serial.println("EN=1");
    return;
  }
  if (cmd == "Z") {
    vertStepper.setCurrentPosition(0);
    horzStepper.setCurrentPosition(0);
    Serial.println("ZEROED");
    return;
  }

  if (cmd == "H+") { moveRel(horzStepper, 4000, "H"); return; }
  if (cmd == "H-") { moveRel(horzStepper, -4000, "H"); return; }
  if (cmd == "V+") { moveRel(vertStepper, 4000, "V"); return; }
  if (cmd == "V-") { moveRel(vertStepper, -4000, "V"); return; }

  if (cmd.startsWith("H")) {
    long s = cmd.substring(1).toInt();
    moveRel(horzStepper, s, "H");
    return;
  }
  if (cmd.startsWith("V")) {
    long s = cmd.substring(1).toInt();
    moveRel(vertStepper, s, "V");
    return;
  }

  Serial.print("UNKNOWN: ");
  Serial.println(cmd);
}

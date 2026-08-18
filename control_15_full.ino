/*
 * =======================================================================================
 * ROBOTIC LAUNCHER FIRMWARE (ESP32) - BLE EDITION
 * =======================================================================================
 * COMMAND REFERENCE:
 * ---------------------------------------------------------------------------------------
 * MASTER:     set v h wl wr          (Set ALL: Vert, Horz, LeftRPM, RightRPM)
 * FEEDER:     shoot                  (Pusher moves FWD until Front Limit Switch)
 * reload                 (Pusher retracts to Back Limit, Dispenser drops ball)
 * SHOOTING:   wl[rpm], wr[rpm], stop, center
 * CALIBRATE:  setzero                (Sets 0,0 for steppers)
 * LIVE TUNE:  jsset[val], jfspeedset[val], jfaccelset[val]
 * MANUAL:     jv[steps], jh[steps], jf[steps], js[0-180] 
 * =======================================================================================
 */

#include <Arduino.h>
#include <ESP32Servo.h>
#include <ESP32Encoder.h>
#include <AccelStepper.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
// --- CONTROL_15 BLE_COMMAND_QUEUE_INCLUDE BEGIN ---
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
// --- CONTROL_15 BLE_COMMAND_QUEUE_INCLUDE END ---

// ==========================================
// 1. CONFIGURATION
// ==========================================

// --- BLE SETTINGS ---
#define SERVICE_UUID           "6E400001-B5A3-F393-E0A9-E50E24DCCA9E" 
#define CHARACTERISTIC_UUID_RX "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_TX "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

BLEServer *pServer = NULL;
BLECharacteristic *pTxCharacteristic;
BLE2902 *pTxCccd = NULL;                 // the descriptor notify() gates on; kept so info can report it
volatile bool deviceConnected = false;   // written by the BLE task, read by loop()
bool oldDeviceConnected = false;
String bleInputBuffer = "";

// --- ENCODERS (Shooter Only) ---
const float PPR_LEFT   = 1000.0;
const float PPR_RIGHT  = 2000.0;

// --- SAFETY ---
const int   MIN_RPM_THRESHOLD  = 200; 
const float MIN_FEED_RPM       = 400.0; // Minimum actual RPM to allow shooting
const char* FIRMWARE_ID = "control_15";

// --- MOTOR CALIBRATION ---
const float LEFT_SLOPE  = 0.1763;
const int   LEFT_OFFSET = 1101;
const float RIGHT_SLOPE = 0.1670;
const int   RIGHT_OFFSET = 1088;

// --- PINS ---
#define VERT_STEP_PUL   25
#define VERT_STEP_DIR   26
#define VERT_STEP_ENA   27

#define HORZ_STEP_PUL   23
#define HORZ_STEP_DIR   22
#define HORZ_STEP_ENA   21 

#define PUSHER_STEP_PUL 4  
#define PUSHER_STEP_DIR 5  
#define PUSHER_STEP_ENA 15 // Using Pin 15 for DRV8825 Enable

#define BLDC1_PIN       13    
#define BLDC2_PIN       12    
#define ENC_BLDC1_A     34
#define ENC_BLDC1_B     35
#define ENC_BLDC2_A     32
#define ENC_BLDC2_B     33

#define FEEDER_SERVO_PIN 19 // Dispenser Servo (Screw Conveyor)

#define LIMIT_FRONT_PIN  18 // Pusher fully extended (Shot fired)
#define LIMIT_BACK_PIN   14 // Pusher fully retracted (Home)
#define LIMIT_BALL_PIN   16 // Ball drop detected from dispenser

// ==========================================
// 2. OBJECTS & VARS
// ==========================================
AccelStepper vertStepper(AccelStepper::DRIVER, VERT_STEP_PUL, VERT_STEP_DIR);
AccelStepper horzStepper(AccelStepper::DRIVER, HORZ_STEP_PUL, HORZ_STEP_DIR);
AccelStepper pusherStepper(AccelStepper::DRIVER, PUSHER_STEP_PUL, PUSHER_STEP_DIR); 

Servo escLeft;
Servo escRight;
Servo feederServo; 

ESP32Encoder encLeft;
ESP32Encoder encRight;

const float STEPS_PER_DEG_VERT = (1000.0 * 60.0) / 360.0; 
const float STEPS_PER_DEG_HORZ = (1000.0 * 50.0) / 360.0; 

// Base State Variables
double targetRPM_Left = 0;
double targetRPM_Right = 0;
double currentRPM_Left = 0;   
double currentRPM_Right = 0;  
int currentPWM_Left = 1000;
int currentPWM_Right = 1000;
int desiredPWM_Left = 1000;
int desiredPWM_Right = 1000;
float targetHorzAngle = 0.0;

unsigned long lastRampTime = 0;

// --- ESC RAMP PACING (control_14) ---
// 5 us every 200 ms is 25 us/s: the rate control_13 actually produced, kept
// exactly. Its nominal 1 us / 25 ms would have been 40 us/s, but the gate never
// ran at 25 ms -- the loop was 40.0 ms, so it fired every iteration. Restoring
// the nominal rate would make the wheels spin up faster than the operator has
// ever seen them, which is a separate decision from fixing the stall.
const unsigned long RAMP_INTERVAL_MS = 200;
const int RAMP_STEP_US = 5;
unsigned long tLeft = 0, tRight = 0;
long cLeft = 0, cRight = 0;

// --- FEEDER STATE MACHINE VARIABLES ---
enum FeederState {
  STATE_IDLE,
  STATE_SHOOTING,
  STATE_RETRACTING,
  STATE_DISPENSING
};
FeederState currentState = STATE_IDLE;

unsigned long dispenseStartTime = 0;

int FEED_SPEED = 80;        // Dispenser forward (NOT const so we can change it live)
const int STOP_SPEED = 90;  // Dispenser stop

float pusherMaxSpeed = 5000.0; 
float pusherAccel = 2000.0;
// --- CONTROL_15 BLE_COMMAND_QUEUE_STATE BEGIN ---
const size_t BLE_COMMAND_MAX_CHARS = 95;
const UBaseType_t BLE_COMMAND_QUEUE_DEPTH = 16;

struct QueuedBleCommand {
  uint32_t epoch;
  char text[BLE_COMMAND_MAX_CHARS + 1];
};

StaticQueue_t bleCommandQueueControl;
uint8_t bleCommandQueueStorage[
    BLE_COMMAND_QUEUE_DEPTH * sizeof(QueuedBleCommand)];
QueueHandle_t bleCommandQueue = NULL;
portMUX_TYPE bleCommandEpochMux = portMUX_INITIALIZER_UNLOCKED;
uint32_t bleCommandEpoch = 0;
// --- CONTROL_15 BLE_COMMAND_QUEUE_STATE END ---
// --- CONTROL_15 RPM_CONTROLLER_STATE BEGIN ---
const double LEFT_KP = 0.12;
const double RIGHT_KP = 0.12;
const double LEFT_KI = 0.08;
const double RIGHT_KI = 0.08;
const double MAX_TRIM_US = 30.0;
const double MAX_TARGET_RPM = 1200.0;
const int PWM_MIN_US = 1000;
const int PWM_MAX_US = 1800;
const double OVERSPEED_RPM = 1300.0;
const unsigned long NO_START_TIMEOUT_MS = 15000;
const unsigned long ENCODER_LOSS_TIMEOUT_MS = 1000;

struct WheelControllerState {
  double lastTarget = 0.0;
  double errorRPM = 0.0;
  int basePWM = PWM_MIN_US;
  double proportionalUs = 0.0;
  double integralUs = 0.0;
  double trimUs = 0.0;
  unsigned long lastSampleMs = 0;
  unsigned long activeSinceMs = 0;
  unsigned long belowFiftySinceMs = 0;
  bool started = false;
  bool exceeded200 = false;
};

WheelControllerState leftController;
WheelControllerState rightController;

enum RpmFault : uint8_t {
  RPM_FAULT_NONE = 0,
  RPM_FAULT_NO_START_L = 1 << 0,
  RPM_FAULT_NO_START_R = 1 << 1,
  RPM_FAULT_ENCODER_LOSS_L = 1 << 2,
  RPM_FAULT_ENCODER_LOSS_R = 1 << 3,
  RPM_FAULT_OVERSPEED_L = 1 << 4,
  RPM_FAULT_OVERSPEED_R = 1 << 5,
};

uint8_t rpmControllerFault = RPM_FAULT_NONE;
bool rpmFaultStopRequested = false;
bool rpmFaultLeftZeroConfirmed = false;
bool rpmFaultRightZeroConfirmed = false;
bool rpmFreshLeft = false;
bool rpmFreshRight = false;

bool targetChangeResets(double oldTarget, double newTarget) {
  if ((oldTarget == 0.0) != (newTarget == 0.0)) return true;
  return oldTarget > 0.0 && newTarget > 0.0
      && fabs(newTarget - oldTarget) > 0.05 * oldTarget;
}

void resetWheelController(WheelControllerState &state, unsigned long now) {
  state.errorRPM = 0.0;
  state.basePWM = PWM_MIN_US;
  state.proportionalUs = 0.0;
  state.integralUs = 0.0;
  state.trimUs = 0.0;
  state.lastSampleMs = 0;
  state.activeSinceMs = now;
  state.belowFiftySinceMs = 0;
  state.started = false;
  state.exceeded200 = false;
}

void noteTargetTransition(WheelControllerState &state,
                          double newTarget,
                          unsigned long now) {
  bool reset = targetChangeResets(state.lastTarget, newTarget);
  if (reset) resetWheelController(state, now);
  state.lastTarget = newTarget;
}

bool parseWheelRpm(const String &token, double &value) {
  const char *start = token.c_str();
  char *end = NULL;
  value = strtod(start, &end);
  return end != start && *end == '\0' && isfinite(value)
      && value >= 0.0 && value <= MAX_TARGET_RPM;
}

void updateWheelController(WheelControllerState &state,
                           double targetRPM,
                           double measuredRPM,
                           double slope,
                           int offset,
                           double kp,
                           double ki,
                           int currentPWM,
                           int &desiredPWM,
                           bool fresh,
                           unsigned long now) {
  if (targetRPM < MIN_RPM_THRESHOLD) {
    state.basePWM = PWM_MIN_US;
    state.errorRPM = 0.0;
    state.proportionalUs = 0.0;
    state.trimUs = 0.0;
    desiredPWM = PWM_MIN_US;
    return;
  }

  state.basePWM = constrain((int)(targetRPM * slope + offset),
                            PWM_MIN_US, PWM_MAX_US);
  if (fresh) {
    double dt = state.lastSampleMs == 0
        ? 0.2 : (now - state.lastSampleMs) / 1000.0;
    state.lastSampleMs = now;
    state.errorRPM = targetRPM - measuredRPM;
    state.proportionalUs = kp * state.errorRPM;

    // The 25 us/s ramp is transport delay inside the loop. Integrating while
    // it is still travelling accumulates correction the plant has not seen.
    bool rampCaught = fabs(desiredPWM - currentPWM) <= RAMP_STEP_US;
    if (rampCaught) {
      double candidateIntegral = constrain(
          state.integralUs + ki * state.errorRPM * dt,
          -MAX_TRIM_US, MAX_TRIM_US);
      double candidateTrim = state.proportionalUs + candidateIntegral;
      double candidatePWM = state.basePWM + candidateTrim;
      bool pushesHigh = candidateTrim > MAX_TRIM_US && state.errorRPM > 0.0;
      bool pushesLow = candidateTrim < -MAX_TRIM_US && state.errorRPM < 0.0;
      bool pushesPwmHigh = candidatePWM > PWM_MAX_US && state.errorRPM > 0.0;
      bool pushesPwmLow = candidatePWM < PWM_MIN_US && state.errorRPM < 0.0;
      if (!pushesHigh && !pushesLow && !pushesPwmHigh && !pushesPwmLow) {
        state.integralUs = candidateIntegral;
      }
    }
  }

  // The encoder timers are independent. Holding the last P/I estimate keeps a
  // sample from one wheel from silently changing the other wheel's output.
  state.trimUs = constrain(state.proportionalUs + state.integralUs,
                           -MAX_TRIM_US, MAX_TRIM_US);
  desiredPWM = constrain(state.basePWM + (int)lround(state.trimUs),
                         PWM_MIN_US, PWM_MAX_US);
}

void appendRpmFaultName(String &name, uint8_t faults,
                        uint8_t bit, const char *label) {
  if ((faults & bit) == 0) return;
  if (name.length() > 0) name += "+";
  name += label;
}

String formatRpmFault(uint8_t faults) {
  if (faults == RPM_FAULT_NONE) return "NONE";
  String name;
  appendRpmFaultName(name, faults, RPM_FAULT_NO_START_L, "NO_START_L");
  appendRpmFaultName(name, faults, RPM_FAULT_NO_START_R, "NO_START_R");
  appendRpmFaultName(name, faults, RPM_FAULT_ENCODER_LOSS_L, "ENCODER_LOSS_L");
  appendRpmFaultName(name, faults, RPM_FAULT_ENCODER_LOSS_R, "ENCODER_LOSS_R");
  appendRpmFaultName(name, faults, RPM_FAULT_OVERSPEED_L, "OVERSPEED_L");
  appendRpmFaultName(name, faults, RPM_FAULT_OVERSPEED_R, "OVERSPEED_R");
  return name;
}

uint8_t evaluateWheelFault(WheelControllerState &state,
                           double targetRPM,
                           double measuredRPM,
                           bool fresh,
                           unsigned long now,
                           uint8_t noStartBit,
                           uint8_t encoderLossBit,
                           uint8_t overspeedBit) {
  if (!fresh) return RPM_FAULT_NONE;

  uint8_t faults = RPM_FAULT_NONE;
  if (measuredRPM > OVERSPEED_RPM) faults |= overspeedBit;

  if (targetRPM < MIN_RPM_THRESHOLD) {
    state.belowFiftySinceMs = 0;
    return faults;
  }

  if (measuredRPM >= 100.0) state.started = true;
  if (measuredRPM > 200.0) state.exceeded200 = true;
  if (!state.started && now - state.activeSinceMs >= NO_START_TIMEOUT_MS) {
    faults |= noStartBit;
  }

  if (targetRPM >= MIN_FEED_RPM && state.exceeded200 && measuredRPM < 50.0) {
    if (state.belowFiftySinceMs == 0) {
      state.belowFiftySinceMs = now;
    } else if (now - state.belowFiftySinceMs >= ENCODER_LOSS_TIMEOUT_MS) {
      faults |= encoderLossBit;
    }
  } else {
    state.belowFiftySinceMs = 0;
  }
  return faults;
}

void latchRpmFault(uint8_t faults, unsigned long now) {
  if (faults == RPM_FAULT_NONE || rpmControllerFault != RPM_FAULT_NONE) return;

  rpmControllerFault = faults;
  rpmFaultStopRequested = false;
  rpmFaultLeftZeroConfirmed = false;
  rpmFaultRightZeroConfirmed = false;
  targetRPM_Left = 0.0;
  targetRPM_Right = 0.0;
  desiredPWM_Left = PWM_MIN_US;
  desiredPWM_Right = PWM_MIN_US;
  resetWheelController(leftController, now);
  resetWheelController(rightController, now);
  leftController.lastTarget = 0.0;
  rightController.lastTarget = 0.0;

  pusherStepper.setCurrentPosition(0);
  pusherStepper.moveTo(0);
  digitalWrite(PUSHER_STEP_ENA, HIGH);
  currentState = STATE_IDLE;
  feederServo.write(STOP_SPEED);
  sendMsg(String("SYS: RPM CTRL FAULT - ") + formatRpmFault(faults));
}

bool clearRpmFaultIfSafe(bool freshLeft, bool freshRight,
                         unsigned long now) {
  if (rpmControllerFault == RPM_FAULT_NONE || !rpmFaultStopRequested) return false;
  if (freshLeft) rpmFaultLeftZeroConfirmed = currentRPM_Left < 50.0;
  if (freshRight) rpmFaultRightZeroConfirmed = currentRPM_Right < 50.0;
  if (!(rpmFaultLeftZeroConfirmed && rpmFaultRightZeroConfirmed)) return false;

  rpmControllerFault = RPM_FAULT_NONE;
  rpmFaultStopRequested = false;
  rpmFaultLeftZeroConfirmed = false;
  rpmFaultRightZeroConfirmed = false;
  resetWheelController(leftController, now);
  resetWheelController(rightController, now);
  leftController.lastTarget = targetRPM_Left;
  rightController.lastTarget = targetRPM_Right;
  return true;
}
// --- CONTROL_15 RPM_CONTROLLER_STATE END ---
// --- CONTROL_15 BLE_COMMAND_QUEUE_ENQUEUE_HELPER BEGIN ---
uint32_t currentBleCommandEpoch() {
  portENTER_CRITICAL(&bleCommandEpochMux);
  uint32_t epoch = bleCommandEpoch;
  portEXIT_CRITICAL(&bleCommandEpochMux);
  return epoch;
}

bool enqueueBleCommand(const String &command) {
  if (bleCommandQueue == NULL || command.length() > BLE_COMMAND_MAX_CHARS) {
    return false;
  }

  QueuedBleCommand queued = {};
  command.toCharArray(queued.text, sizeof(queued.text));
  String normalized = command;
  normalized.trim();

  if (normalized.equalsIgnoreCase("stop")) {
    portENTER_CRITICAL(&bleCommandEpochMux);
    queued.epoch = ++bleCommandEpoch;
    portEXIT_CRITICAL(&bleCommandEpochMux);
    xQueueReset(bleCommandQueue);
    return xQueueSendToFront(bleCommandQueue, &queued, 0) == pdTRUE;
  }
  queued.epoch = currentBleCommandEpoch();
  return xQueueSendToBack(bleCommandQueue, &queued, 0) == pdTRUE;
}
// --- CONTROL_15 BLE_COMMAND_QUEUE_ENQUEUE_HELPER END ---

// ==========================================
// 3. BLE CALLBACKS & HELPERS
// ==========================================

volatile uint16_t bleNegotiatedMtu = 23;  // ATT default; notify() truncates above mtu-3 bytes
volatile int bleLastNotifyStatus = -1;
volatile uint32_t bleLastNotifyCode = 0;
volatile uint32_t bleNotifyAttempts = 0;

const char* bleNotifyStatusName(int status) {
    switch (status) {
      case BLECharacteristicCallbacks::SUCCESS_INDICATE: return "SUCCESS_INDICATE";
      case BLECharacteristicCallbacks::SUCCESS_NOTIFY: return "SUCCESS_NOTIFY";
      case BLECharacteristicCallbacks::ERROR_INDICATE_DISABLED: return "ERROR_INDICATE_DISABLED";
      case BLECharacteristicCallbacks::ERROR_NOTIFY_DISABLED: return "ERROR_NOTIFY_DISABLED";
      case BLECharacteristicCallbacks::ERROR_GATT: return "ERROR_GATT";
      case BLECharacteristicCallbacks::ERROR_NO_CLIENT: return "ERROR_NO_CLIENT";
      case BLECharacteristicCallbacks::ERROR_NO_SUBSCRIBER: return "ERROR_NO_SUBSCRIBER";
      case BLECharacteristicCallbacks::ERROR_INDICATE_TIMEOUT: return "ERROR_INDICATE_TIMEOUT";
      case BLECharacteristicCallbacks::ERROR_INDICATE_FAILURE: return "ERROR_INDICATE_FAILURE";
      default: return "NONE";
    }
}

class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) override {
      deviceConnected = true;
    };
    void onDisconnect(BLEServer* pServer) override {
      deviceConnected = false;
    }
    // Recorded, not polled: BLEServer::getPeerMTU() dereferences map::end() when the
    // conn_id is absent, which is not something to risk from a command handler.
    void onMtuChanged(BLEServer* pServer, esp_ble_gatts_cb_param_t *param) override {
      bleNegotiatedMtu = param->mtu.mtu;
    }
};

class MyTxCallbacks: public BLECharacteristicCallbacks {
    void onNotify(BLECharacteristic *pCharacteristic) override {
      bleNotifyAttempts++;
    }
    void onStatus(BLECharacteristic *pCharacteristic, Status status, uint32_t code) override {
      // The library's log_v/log_e diagnostics are compiled out at DebugLevel=none.
      // Retain the decision as data and report it over USB in the next info block.
      bleLastNotifyStatus = static_cast<int>(status);
      bleLastNotifyCode = code;
    }
};

void sendMsg(String msg) {
    Serial.println(msg);            // USB is unconditional - the control_13 contract
    if (deviceConnected) {
        pTxCharacteristic->setValue((uint8_t*)msg.c_str(), msg.length());
        pTxCharacteristic->notify();
    }
}

double getRPM(ESP32Encoder &enc, float ppr, unsigned long &lastTime, long &lastCount) {
  long currentCount = enc.getCount();
  unsigned long currentTime = millis();
  
  if (currentTime - lastTime >= 200) { 
    long countDiff = currentCount - lastCount;
    double rpm = ((double)countDiff / ppr * 60000.0) / (currentTime - lastTime);
    lastCount = currentCount; lastTime = currentTime;
    return abs(rpm);
  }
  return -1; 
}

void updateMotorPWM() {
    unsigned long now = millis();
    if (rpmControllerFault != RPM_FAULT_NONE) {
        desiredPWM_Left = PWM_MIN_US;
        desiredPWM_Right = PWM_MIN_US;
        clearRpmFaultIfSafe(rpmFreshLeft, rpmFreshRight, now);
        rpmFreshLeft = false;
        rpmFreshRight = false;
        return;
    }

    updateWheelController(leftController, targetRPM_Left, currentRPM_Left,
                          LEFT_SLOPE, LEFT_OFFSET, LEFT_KP, LEFT_KI,
                          currentPWM_Left, desiredPWM_Left, rpmFreshLeft, now);
    updateWheelController(rightController, targetRPM_Right, currentRPM_Right,
                          RIGHT_SLOPE, RIGHT_OFFSET, RIGHT_KP, RIGHT_KI,
                          currentPWM_Right, desiredPWM_Right, rpmFreshRight, now);

    uint8_t faults = RPM_FAULT_NONE;
    faults |= evaluateWheelFault(leftController, targetRPM_Left, currentRPM_Left,
                                 rpmFreshLeft, now, RPM_FAULT_NO_START_L,
                                 RPM_FAULT_ENCODER_LOSS_L, RPM_FAULT_OVERSPEED_L);
    faults |= evaluateWheelFault(rightController, targetRPM_Right, currentRPM_Right,
                                 rpmFreshRight, now, RPM_FAULT_NO_START_R,
                                 RPM_FAULT_ENCODER_LOSS_R, RPM_FAULT_OVERSPEED_R);
    latchRpmFault(faults, now);
    rpmFreshLeft = false;
    rpmFreshRight = false;
}

// ==========================================
// 4. COMMAND PROCESSOR
// ==========================================
void processCommand(String cmd) {
    cmd.trim();
    cmd.toLowerCase(); // Forces everything to lowercase instantly for strict matching
    
    if (cmd.startsWith("set ")) {
        int firstSpace = cmd.indexOf(' ');
        int secondSpace = cmd.indexOf(' ', firstSpace + 1);
        int thirdSpace = cmd.indexOf(' ', secondSpace + 1);
        int fourthSpace = cmd.indexOf(' ', thirdSpace + 1);

        if (firstSpace > 0 && secondSpace > 0 && thirdSpace > 0) {
            String vStr = cmd.substring(firstSpace + 1, secondSpace);
            String hStr = cmd.substring(secondSpace + 1, thirdSpace);
            String wlStr = cmd.substring(thirdSpace + 1, fourthSpace > 0 ? fourthSpace : cmd.length());
            String wrStr = (fourthSpace > 0) ? cmd.substring(fourthSpace + 1) : "0"; 

            // --- CONTROL_15 SET_TARGET_VALIDATION BEGIN ---
            double checkedLeft = 0.0;
            double checkedRight = 0.0;
            if (!parseWheelRpm(wlStr, checkedLeft)
                || !parseWheelRpm(wrStr, checkedRight)) {
                sendMsg("ERR: RPM RANGE");
                return;
            }
            // --- CONTROL_15 SET_TARGET_VALIDATION END ---
            float vDeg = vStr.toFloat();
            float hDeg = hStr.toFloat();

            vDeg = constrain(vDeg, -30.0, 30.0);
            hDeg = constrain(hDeg, -30.0, 30.0);

            targetRPM_Left = wlStr.toDouble();
            targetRPM_Right = wrStr.toDouble();

            // --- CONTROL_15 SET_TARGET_TRANSITION BEGIN ---
            noteTargetTransition(leftController, targetRPM_Left, millis());
            noteTargetTransition(rightController, targetRPM_Right, millis());
            // --- CONTROL_15 SET_TARGET_TRANSITION END ---
            vertStepper.moveTo(vDeg * STEPS_PER_DEG_VERT);
            targetHorzAngle = hDeg;
            horzStepper.moveTo(targetHorzAngle * STEPS_PER_DEG_HORZ);

            updateMotorPWM();
            
            char buffer[100];
            sprintf(buffer, "ACK: V=%.1f H=%.1f", vDeg, hDeg);
            sendMsg(buffer);
        }
    }
    
    // --- 1. LIVE TUNING COMMANDS (Checked first to avoid prefix collisions) ---
    else if (cmd.startsWith("jsset")) { 
        int val = cmd.substring(5).toInt();
        FEED_SPEED = constrain(val, 0, 180); 
        sendMsg("CFG: Servo feed speed set to " + String(FEED_SPEED));
    }
    else if (cmd.startsWith("jfspeedset")) { 
        float val = cmd.substring(10).toFloat();
        pusherMaxSpeed = val;
        pusherStepper.setMaxSpeed(pusherMaxSpeed);
        sendMsg("CFG: Pusher max speed set to " + String(pusherMaxSpeed));
    }
    else if (cmd.startsWith("jfaccelset")) { 
        float val = cmd.substring(10).toFloat();
        pusherAccel = val;
        pusherStepper.setAcceleration(pusherAccel);
        sendMsg("CFG: Pusher accel set to " + String(pusherAccel));
    }

    // --- 2. MANUAL JOG & UTILS ---
    else if (cmd.startsWith("jv")) { 
        long steps = cmd.substring(2).toInt();
        vertStepper.move(steps);
        sendMsg("MANUAL: Jog Vert " + String(steps));
    }
    else if (cmd.startsWith("jh")) { 
        long steps = cmd.substring(2).toInt();
        horzStepper.move(steps);
        sendMsg("MANUAL: Jog Horz " + String(steps));
    }
    else if (cmd.startsWith("js")) { 
        int val = cmd.substring(2).toInt();
        val = constrain(val, 0, 180); 
        feederServo.write(val);
        sendMsg("MANUAL: Feeder Servo set to " + String(val));
    }
    else if (cmd.startsWith("jf")) { 
        long steps = cmd.substring(2).toInt();
        pusherStepper.move(steps);
        sendMsg("MANUAL: Jog Feeder (Pusher) " + String(steps));
    }
    
    // --- 3. SHOOT & RELOAD COMMANDS ---
    else if (cmd.equalsIgnoreCase("shoot")) {
        // --- CONTROL_15 SHOOT_FAULT_GATE BEGIN ---
        if (rpmControllerFault != RPM_FAULT_NONE) {
          sendMsg("CMD: SHOOT BLOCKED - RPM CTRL FAULT");
          return;
        }
        // --- CONTROL_15 SHOOT_FAULT_GATE END ---
        currentState = STATE_SHOOTING;
        sendMsg("CMD: SHOOT (Waiting for RPM)");
    }
    else if (cmd.equalsIgnoreCase("reload")) {
        currentState = STATE_RETRACTING;

        // Tell the aiming steppers to return to center (0,0)
        vertStepper.moveTo(7);
        horzStepper.moveTo(0);
        targetHorzAngle = 0.0; 

        // Spin down the flywheels safely
        targetRPM_Left = 0;
        targetRPM_Right = 0;
        // --- CONTROL_15 RELOAD_TARGET_TRANSITION BEGIN ---
        resetWheelController(leftController, millis());
        resetWheelController(rightController, millis());
        leftController.lastTarget = 0.0;
        rightController.lastTarget = 0.0;
        // --- CONTROL_15 RELOAD_TARGET_TRANSITION END ---
        updateMotorPWM(); 
        
        sendMsg("CMD: RELOAD - RETRACTING, HOMING & MOTORS OFF");
    }
    
    else if (cmd.equalsIgnoreCase("setzero")) {
        vertStepper.setCurrentPosition(0); 
        horzStepper.setCurrentPosition(0);
        vertStepper.moveTo(0);             
        horzStepper.moveTo(0);
        targetHorzAngle = 0;
        sendMsg("ZERO SET");
    }
    else if (cmd.equalsIgnoreCase("center")) {
        vertStepper.moveTo(0);
        horzStepper.moveTo(0);
        targetHorzAngle = 0.0;
        sendMsg("CMD: CENTERED (V=0, H=0)");
    }
    else if (cmd.equalsIgnoreCase("stop")) {
        vertStepper.stop(); horzStepper.stop(); 
        
        // Instant Stop Trick for the Pusher
        pusherStepper.setCurrentPosition(0); 
        pusherStepper.moveTo(0); 
        
        vertStepper.moveTo(vertStepper.currentPosition());
        horzStepper.moveTo(horzStepper.currentPosition());
        targetRPM_Left = 0; targetRPM_Right = 0;
        // --- CONTROL_15 STOP_TARGET_TRANSITION BEGIN ---
        resetWheelController(leftController, millis());
        resetWheelController(rightController, millis());
        leftController.lastTarget = 0.0;
        rightController.lastTarget = 0.0;
        if (rpmControllerFault != RPM_FAULT_NONE) {
          rpmFaultStopRequested = true;
          rpmFaultLeftZeroConfirmed = false;
          rpmFaultRightZeroConfirmed = false;
        }
        // --- CONTROL_15 STOP_TARGET_TRANSITION END ---
        updateMotorPWM();
        
        currentState = STATE_IDLE; 
        feederServo.write(STOP_SPEED); 
        sendMsg("STOPPED ALL");
    }
    else if (cmd.equalsIgnoreCase("info")) {
        float currentVDeg = vertStepper.currentPosition() / STEPS_PER_DEG_VERT;
        float currentHDeg = horzStepper.currentPosition() / STEPS_PER_DEG_HORZ;

        String stateStr = "UNKNOWN";
        switch(currentState) {
            case STATE_IDLE:       stateStr = "IDLE"; break;
            case STATE_SHOOTING:   stateStr = "SHOOTING"; break;
            case STATE_RETRACTING: stateStr = "RETRACTING"; break;
            case STATE_DISPENSING: stateStr = "DISPENSING"; break;
        }

        // Declare all buffers exactly ONCE
        char buf0[40], buf1[60], buf2[60], buf3[60], buf4[60], buf5[60];

        sprintf(buf0, "INFO | FW: %s", FIRMWARE_ID);
        sendMsg(String(buf0));
        
        sprintf(buf1, "INFO | Ang: V=%.1f deg, H=%.1f deg", currentVDeg, currentHDeg);
        sendMsg(String(buf1));
        
        sprintf(buf2, "INFO | RPM: L=%.0f/%.0f, R=%.0f/%.0f", currentRPM_Left, targetRPM_Left, currentRPM_Right, targetRPM_Right);
        sendMsg(String(buf2));
        
        sprintf(buf3, "INFO | FDR: %s, PUSH_POS: %ld", stateStr.c_str(), pusherStepper.currentPosition());
        sendMsg(String(buf3));

        sprintf(buf4, "INFO | LMT: Front=%s, Back=%s, Ball=%s", 
                digitalRead(LIMIT_FRONT_PIN) ? "HIGH" : "LOW",
                digitalRead(LIMIT_BACK_PIN)  ? "HIGH" : "LOW",
                digitalRead(LIMIT_BALL_PIN)  ? "HIGH" : "LOW");
        sendMsg(String(buf4));

        sprintf(buf5, "INFO | CFG: SrvSpd=%d, PshSpd=%.0f, PshAcc=%.0f",
                FEED_SPEED, pusherMaxSpeed, pusherAccel);
        sendMsg(String(buf5));

        // The values notify() gates on, its own last result, and the MTU that
        // constrains a notification. This line is diagnostic evidence over USB;
        // it deliberately does not change BLE pacing while the cause is unknown.
        // Without these a silent BLE link is indistinguishable from a dead one.
        char buf6[160];
        unsigned int cccd = 0;
        if (pTxCccd != NULL) {
            uint8_t *v = pTxCccd->getValue();
            if (v != NULL) cccd = (unsigned int)v[0] | ((unsigned int)v[1] << 8);
        }
        int notifyStatus = bleLastNotifyStatus;
        uint32_t notifyCode = bleLastNotifyCode;
        uint32_t notifyAttempts = bleNotifyAttempts;
        snprintf(buf6, sizeof(buf6),
                "INFO | BLE: conn=%d, cccd=0x%04X, clients=%lu, mtu=%u, notify=%s, code=%lu, attempts=%lu",
                deviceConnected ? 1 : 0,
                cccd,
                (unsigned long)(pServer != NULL ? pServer->getConnectedCount() : 0),
                (unsigned int)bleNegotiatedMtu,
                bleNotifyStatusName(notifyStatus),
                (unsigned long)notifyCode,
                (unsigned long)notifyAttempts);
        sendMsg(String(buf6));
        // --- CONTROL_15 INFO_CONTROLLER_DIAGNOSTIC BEGIN ---
        char buf7[120];
        String rpmFaultName = formatRpmFault(rpmControllerFault);
        snprintf(buf7, sizeof(buf7),
                "INFO | CTRL: PL=%d PR=%d IL=%.2f IR=%.2f FAULT=%s",
                currentPWM_Left, currentPWM_Right,
                leftController.trimUs, rightController.trimUs,
                rpmFaultName.c_str());
        sendMsg(String(buf7));
        // --- CONTROL_15 INFO_CONTROLLER_DIAGNOSTIC END ---
    }
}
// --- CONTROL_15 BLE_COMMAND_QUEUE_DRAIN_HELPER BEGIN ---
void processOneQueuedBleCommand() {
    if (bleCommandQueue == NULL) return;
    QueuedBleCommand queued = {};
    if (xQueueReceive(bleCommandQueue, &queued, 0) == pdTRUE) {
        if (queued.epoch != currentBleCommandEpoch()) return;
        processCommand(String(queued.text));
    }
}
// --- CONTROL_15 BLE_COMMAND_QUEUE_DRAIN_HELPER END ---

class MyCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
      String rxValue = pCharacteristic->getValue(); 
      if (rxValue.length() > 0) {
        for (int i = 0; i < rxValue.length(); i++) {
          char c = rxValue[i];
          if (c == '\n') {
            // --- CONTROL_15 BLE_COMMAND_QUEUE_ENQUEUE BEGIN ---
            enqueueBleCommand(bleInputBuffer);
            // --- CONTROL_15 BLE_COMMAND_QUEUE_ENQUEUE END ---
            bleInputBuffer = ""; 
          } else if (c != '\r') {
            bleInputBuffer += c; 
          }
        }
      }
    }
};

// ==========================================
// 5. SETUP
// ==========================================
void setup() {
  Serial.begin(921600);
  Serial.println("SYS: FW control_15 READY");
  // --- CONTROL_15 BLE_COMMAND_QUEUE_SETUP BEGIN ---
  bleCommandQueue = xQueueCreateStatic(
      BLE_COMMAND_QUEUE_DEPTH, sizeof(QueuedBleCommand),
      bleCommandQueueStorage, &bleCommandQueueControl);
  if (bleCommandQueue == NULL) {
    Serial.println("SYS: BLE COMMAND QUEUE INIT FAILED");
    while (true) delay(1000);
  }
  // --- CONTROL_15 BLE_COMMAND_QUEUE_SETUP END ---

  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  // Initialize Limit Switches
  pinMode(LIMIT_FRONT_PIN, INPUT_PULLUP);
  pinMode(LIMIT_BACK_PIN, INPUT_PULLUP);
  pinMode(LIMIT_BALL_PIN, INPUT_PULLUP);

  pinMode(17, OUTPUT); // this is for the rst and slp pins of drv8825 
  digitalWrite(17, HIGH);

  // Setup Pusher Stepper Enable (DRV8825: HIGH = OFF/Idle)
  pinMode(PUSHER_STEP_ENA, OUTPUT);
  digitalWrite(PUSHER_STEP_ENA, HIGH); 

  BLEDevice::init("RoboLauncher");
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService *pService = pServer->createService(SERVICE_UUID);
  pTxCharacteristic = pService->createCharacteristic(
                        CHARACTERISTIC_UUID_TX,
                        BLECharacteristic::PROPERTY_NOTIFY
                      );
  pTxCccd = new BLE2902();   // kept: this is the descriptor notify() reads before sending
  pTxCharacteristic->addDescriptor(pTxCccd);
  pTxCharacteristic->setCallbacks(new MyTxCallbacks());

  BLECharacteristic *pRxCharacteristic = pService->createCharacteristic(
                         CHARACTERISTIC_UUID_RX,
                         BLECharacteristic::PROPERTY_WRITE
                       );
  pRxCharacteristic->setCallbacks(new MyCallbacks());

  pService->start();
  pServer->getAdvertising()->start();
  Serial.println("SYS: BLE Advertising... Waiting for connection.");

  pinMode(ENC_BLDC1_A, INPUT_PULLUP); pinMode(ENC_BLDC1_B, INPUT_PULLUP);
  pinMode(ENC_BLDC2_A, INPUT_PULLUP); pinMode(ENC_BLDC2_B, INPUT_PULLUP);
  encLeft.attachHalfQuad(ENC_BLDC1_A, ENC_BLDC1_B);
  encRight.attachHalfQuad(ENC_BLDC2_A, ENC_BLDC2_B);
  encLeft.clearCount(); encRight.clearCount();

  pinMode(VERT_STEP_ENA, OUTPUT); pinMode(HORZ_STEP_ENA, OUTPUT);
  digitalWrite(VERT_STEP_ENA, HIGH); 
  digitalWrite(HORZ_STEP_ENA, HIGH); 
  vertStepper.setMaxSpeed(18000); vertStepper.setAcceleration(12000);
  horzStepper.setMaxSpeed(12000); horzStepper.setAcceleration(8000);

  pusherStepper.setMaxSpeed(pusherMaxSpeed);
  pusherStepper.setAcceleration(pusherAccel);

  escLeft.setPeriodHertz(50);
  escRight.setPeriodHertz(50);
  escLeft.attach(BLDC1_PIN, 1000, 2000);
  escRight.attach(BLDC2_PIN, 1000, 2000);
  escLeft.writeMicroseconds(1000);
  escRight.writeMicroseconds(1000);

  feederServo.setPeriodHertz(80); 
  feederServo.attach(FEEDER_SERVO_PIN, 500, 2400); 
  feederServo.write(STOP_SPEED); 

  delay(3000); 
}

// ==========================================
// 6. MAIN LOOP
// ==========================================
void loop() {
  // --- CONTROL_15 BLE_COMMAND_QUEUE_DRAIN BEGIN ---
  processOneQueuedBleCommand();
  // --- CONTROL_15 BLE_COMMAND_QUEUE_DRAIN END ---
  // --- REAL-TIME RPM TRACKING ---
  double tempL = getRPM(encLeft, PPR_LEFT, tLeft, cLeft);
  if (tempL != -1) currentRPM_Left = tempL;

  double tempR = getRPM(encRight, PPR_RIGHT, tRight, cRight);
  if (tempR != -1) currentRPM_Right = tempR;

  // --- CONTROL_15 RPM_FRESH_SAMPLE_UPDATE BEGIN ---
  rpmFreshLeft = tempL != -1;
  rpmFreshRight = tempR != -1;
  if (rpmFreshLeft || rpmFreshRight) updateMotorPWM();
  // --- CONTROL_15 RPM_FRESH_SAMPLE_UPDATE END ---
  // --- FEEDER STATE MACHINE ---
  switch(currentState) {
      
      case STATE_IDLE:
          // DRV8825 Logic: LOW = ON (Moving), HIGH = OFF (Resting)
          if (pusherStepper.distanceToGo() != 0) {
              digitalWrite(PUSHER_STEP_ENA, LOW); // Turn motor ON to move
          } 
          else {
              digitalWrite(PUSHER_STEP_ENA, HIGH); // Turn motor OFF to rest & cool down!
          }
          break;

      case STATE_SHOOTING:
          // --- CONTROL_15 SHOOTING_FAULT_GATE BEGIN ---
          if (rpmControllerFault != RPM_FAULT_NONE) {
              pusherStepper.setCurrentPosition(0);
              pusherStepper.moveTo(0);
              currentState = STATE_IDLE;
              break;
          }
          // --- CONTROL_15 SHOOTING_FAULT_GATE END ---
          digitalWrite(PUSHER_STEP_ENA, LOW); // FORCE MOTOR ON!
          
          if (currentRPM_Left >= MIN_FEED_RPM && currentRPM_Right >= MIN_FEED_RPM) {
              if (pusherStepper.distanceToGo() == 0) {
                  pusherStepper.move(-100000); 
              }
              if (digitalRead(LIMIT_FRONT_PIN) == LOW) {
                  pusherStepper.setCurrentPosition(0); 
                  pusherStepper.moveTo(0);             
                  currentState = STATE_IDLE;
                  sendMsg("SYS: SHOT FIRED - FRONT LIMIT HIT");
              }
          } else {
              pusherStepper.setCurrentPosition(0);
              pusherStepper.moveTo(0);
          }
          break;

      case STATE_RETRACTING:
          digitalWrite(PUSHER_STEP_ENA, LOW); // FORCE MOTOR ON!
          
          if (pusherStepper.distanceToGo() == 0) {
              pusherStepper.move(100000); 
          }
          
          if (digitalRead(LIMIT_BACK_PIN) == LOW) {
              pusherStepper.setCurrentPosition(0); 
              pusherStepper.moveTo(0);             
              
              currentState = STATE_DISPENSING;
              dispenseStartTime = millis(); 
              feederServo.write(FEED_SPEED); 
              sendMsg("SYS: RETRACTED - DISPENSING BALL");
          }
          break;

      case STATE_DISPENSING:
          if (digitalRead(LIMIT_BALL_PIN) == LOW) {
              feederServo.write(STOP_SPEED);
              currentState = STATE_IDLE;
              sendMsg("SYS: RELOAD DONE - BALL DETECTED");
          } 
          else if (millis() - dispenseStartTime >= 10000) {
              feederServo.write(STOP_SPEED);
              currentState = STATE_IDLE;
              sendMsg("SYS: RELOAD DONE - TIMEOUT");
          }
          break;
  }

  // --- BLE MANAGEMENT ---
  // Transitions are printed HERE, not in the callbacks: those run in the BLE task
  // and Serial from two tasks interleaves mid-line. USB is the only channel that
  // can report on BLE, so a connect that never happens must be visible.
  if (!deviceConnected && oldDeviceConnected) {
      Serial.println("SYS: BLE DISCONNECTED");
      delay(500);
      pServer->startAdvertising();
      oldDeviceConnected = deviceConnected;
  }
  if (deviceConnected && !oldDeviceConnected) {
      Serial.println("SYS: BLE CONNECTED");
      oldDeviceConnected = deviceConnected;
  }

  // --- USB BACKUP ---
  if (Serial.available()) {
      String cmd = Serial.readStringUntil('\n');
      processCommand(cmd);
  }

  // --- ESC RAMPING ---
  // Each writeMicroseconds() reaches ledc_update_duty(), which on classic ESP32
  // under IDF v5.5.2 actively waits for conf1.duty_start to clear -- one 50 Hz
  // PWM period, 20 ms. Two of them made every loop 40.0 ms (measured 2026-08-13,
  // 19 intervals, stdev 0.108 ms), so the old 25 ms gate was satisfied on EVERY
  // iteration and AccelStepper, which emits at most one step per run(), was
  // capped at 25 steps/s against a 12000 step/s profile.
  //
  // Both changes only reduce how OFTEN a duty is written; neither changes the
  // ramp rate, its endpoints, or the 1000 us rest value:
  //   - a write happens only when the value actually changed, so idle costs zero;
  //   - the interval is RAMP_INTERVAL_MS with a RAMP_STEP_US step, chosen to hold
  //     the 25 us/s that control_13 actually produced.
  // The stall now occupies 40 ms out of every 200 ms instead of all of it, so the
  // steppers get ~80% of the time even while the wheels are ramping.
  if (millis() - lastRampTime > RAMP_INTERVAL_MS) {
    lastRampTime = millis();

    int deltaLeft = desiredPWM_Left - currentPWM_Left;
    if (deltaLeft != 0) {
      currentPWM_Left += constrain(deltaLeft, -RAMP_STEP_US, RAMP_STEP_US);
      escLeft.writeMicroseconds(currentPWM_Left);
    }

    int deltaRight = desiredPWM_Right - currentPWM_Right;
    if (deltaRight != 0) {
      currentPWM_Right += constrain(deltaRight, -RAMP_STEP_US, RAMP_STEP_US);
      escRight.writeMicroseconds(currentPWM_Right);
    }
  }

  // --- STEPPER EXECUTION ---
  vertStepper.run();
  horzStepper.run();
  // --- CONTROL_15 PUSHER_FAULT_INTERLOCK BEGIN ---
  if (rpmControllerFault == RPM_FAULT_NONE) {
    pusherStepper.run();
  } else {
    pusherStepper.setCurrentPosition(0);
    pusherStepper.moveTo(0);
    digitalWrite(PUSHER_STEP_ENA, HIGH);
  }
  // --- CONTROL_15 PUSHER_FAULT_INTERLOCK END ---

  // --- TELEMETRY ---
  static unsigned long lastTelem = 0;

  // USB telemetry is evidence for both coast-down and a fresh zero. BLE notify
  // remains conditional inside sendMsg(); USB Serial.println() is unconditional.
  // Keep this out of pusher motion so the cooperative feeder loop stays primary.
  if (millis() - lastTelem > 250 && currentState == STATE_IDLE) {
    lastTelem = millis();
    char buffer[50];
    sprintf(buffer, "L:%.0f R:%.0f", currentRPM_Left, currentRPM_Right);
    sendMsg(buffer);
  }
}

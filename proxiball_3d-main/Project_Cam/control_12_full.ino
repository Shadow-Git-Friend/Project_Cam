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

// ==========================================
// 1. CONFIGURATION
// ==========================================

// --- BLE SETTINGS ---
#define SERVICE_UUID           "6E400001-B5A3-F393-E0A9-E50E24DCCA9E" 
#define CHARACTERISTIC_UUID_RX "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_TX "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

BLEServer *pServer = NULL;
BLECharacteristic *pTxCharacteristic;
bool deviceConnected = false;
bool oldDeviceConnected = false;
String bleInputBuffer = ""; 

// --- ENCODERS (Shooter Only) ---
const float PPR_LEFT   = 1000.0;
const float PPR_RIGHT  = 2000.0;

// --- SAFETY ---
const int   MIN_RPM_THRESHOLD  = 200; 
const float MIN_FEED_RPM       = 400.0; // Minimum actual RPM to allow shooting

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

// ==========================================
// 3. BLE CALLBACKS & HELPERS
// ==========================================

class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      deviceConnected = true;
      BLEDevice::startAdvertising(); 
    };
    void onDisconnect(BLEServer* pServer) {
      deviceConnected = false;
    }
};

void sendMsg(String msg) {
    Serial.println(msg); 
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
    if (targetRPM_Left < MIN_RPM_THRESHOLD) desiredPWM_Left = 1000;
    else desiredPWM_Left = constrain((int)((targetRPM_Left * LEFT_SLOPE) + LEFT_OFFSET), 1000, 1800);

    if (targetRPM_Right < MIN_RPM_THRESHOLD) desiredPWM_Right = 1000;
    else desiredPWM_Right = constrain((int)((targetRPM_Right * RIGHT_SLOPE) + RIGHT_OFFSET), 1000, 1800);
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

            float vDeg = vStr.toFloat();
            float hDeg = hStr.toFloat();

            vDeg = constrain(vDeg, -30.0, 30.0);
            hDeg = constrain(hDeg, -30.0, 30.0);

            targetRPM_Left = wlStr.toDouble();
            targetRPM_Right = wrStr.toDouble();

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
        char buf1[60], buf2[60], buf3[60], buf4[60], buf5[60]; 
        
        sprintf(buf1, "INFO | Ang: V=%.1f deg, H=%.1f deg", currentVDeg, currentHDeg);
        sendMsg(String(buf1));
        delay(50); 
        
        sprintf(buf2, "INFO | RPM: L=%.0f/%.0f, R=%.0f/%.0f", currentRPM_Left, targetRPM_Left, currentRPM_Right, targetRPM_Right);
        sendMsg(String(buf2));
        delay(50);
        
        sprintf(buf3, "INFO | FDR: %s, PUSH_POS: %ld", stateStr.c_str(), pusherStepper.currentPosition());
        sendMsg(String(buf3));
        delay(50);

        sprintf(buf4, "INFO | LMT: Front=%s, Back=%s, Ball=%s", 
                digitalRead(LIMIT_FRONT_PIN) ? "HIGH" : "LOW",
                digitalRead(LIMIT_BACK_PIN)  ? "HIGH" : "LOW",
                digitalRead(LIMIT_BALL_PIN)  ? "HIGH" : "LOW");
        sendMsg(String(buf4));
        delay(50);

        sprintf(buf5, "INFO | CFG: SrvSpd=%d, PshSpd=%.0f, PshAcc=%.0f", 
                FEED_SPEED, pusherMaxSpeed, pusherAccel);
        sendMsg(String(buf5));
    }
}

class MyCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
      String rxValue = pCharacteristic->getValue(); 
      if (rxValue.length() > 0) {
        for (int i = 0; i < rxValue.length(); i++) {
          char c = rxValue[i];
          if (c == '\n') {
            processCommand(bleInputBuffer);
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
  pTxCharacteristic->addDescriptor(new BLE2902());

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
  // --- REAL-TIME RPM TRACKING ---
  double tempL = getRPM(encLeft, PPR_LEFT, tLeft, cLeft);
  if (tempL != -1) currentRPM_Left = tempL;

  double tempR = getRPM(encRight, PPR_RIGHT, tRight, cRight);
  if (tempR != -1) currentRPM_Right = tempR;

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
  if (!deviceConnected && oldDeviceConnected) {
      delay(500); 
      pServer->startAdvertising(); 
      oldDeviceConnected = deviceConnected;
  }
  if (deviceConnected && !oldDeviceConnected) {
      oldDeviceConnected = deviceConnected;
  }

  // --- USB BACKUP ---
  if (Serial.available()) {
      String cmd = Serial.readStringUntil('\n');
      processCommand(cmd);
  }

  // --- ESC RAMPING ---
  if (millis() - lastRampTime > 25) {
    lastRampTime = millis();
    if (currentPWM_Left < desiredPWM_Left) currentPWM_Left++;
    else if (currentPWM_Left > desiredPWM_Left) currentPWM_Left--;
    escLeft.writeMicroseconds(currentPWM_Left);

    if (currentPWM_Right < desiredPWM_Right) currentPWM_Right++;
    else if (currentPWM_Right > desiredPWM_Right) currentPWM_Right--;
    escRight.writeMicroseconds(currentPWM_Right);
  }

  // --- STEPPER EXECUTION ---
  vertStepper.run();
  horzStepper.run();
  pusherStepper.run(); 

 // --- TELEMETRY ---
  if (deviceConnected) {
     static unsigned long lastTelem = 0;
     
     // FIX: Only send telemetry if the pusher is NOT moving
     if (millis() - lastTelem > 250 && currentState == STATE_IDLE) { 
        lastTelem = millis();
        if (currentPWM_Left > 1050 || currentPWM_Right > 1050 || horzStepper.distanceToGo() != 0) {
           char buffer[50];
           sprintf(buffer, "L:%.0f R:%.0f", currentRPM_Left, currentRPM_Right);
           sendMsg(buffer);
        }
     }
  }
}
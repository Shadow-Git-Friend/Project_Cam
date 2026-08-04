import math
import serial
import time
import sys

# --- CONFIGURATION ---
SERIAL_PORT = 'COM16'  #set to your working COM port!
BAUD_RATE = 115200
G = 9.81              # Gravity (m/s^2)
Z_LAUNCHER = 0.50    # Height of the launcher (m)

# 25cm wheel diameter conversion: V(m/s) * 60 / (0.25 * PI)
VELOCITY_TO_RPM_MULTIPLIER = 80   #76.39 

def connect_serial():
    try:
        print(f"Connecting to ESP32 on {SERIAL_PORT} at {BAUD_RATE} baud...")
        esp32 = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # Give the ESP32 a moment to reset after serial connection
        print("Connected successfully!\n")
        return esp32
    except serial.SerialException as e:
        print(f"Error connecting to Serial Port: {e}")
        print("Check your cable and ensure the Arduino IDE Serial Monitor is CLOSED.")
        sys.exit(1)

def calculate_kinematics(x, y, z, v_ms):
    """Calculates pan and tilt angles to hit coordinate (X,Y,Z) at velocity V in m/s."""
    # 1. Pan Angle (Horizontal)
    h_rad = math.atan2(x, y)
    h_deg = math.degrees(h_rad)
    
    # 2. Distance and Delta Z
    d = math.sqrt(x**2 + y**2)
    delta_z = z - Z_LAUNCHER
    
    # 3. Tilt Angle (Vertical)
    discriminant = v_ms**4 - G * (G * d**2 + 2 * delta_z * v_ms**2)
    
    if discriminant < 0:
        print(f"\n[!] TARGET UNREACHABLE: Velocity is too slow to hit this target.")
        return None, None
        
    v_rad = math.atan((v_ms**2 - math.sqrt(discriminant)) / (G * d))
    v_deg = math.degrees(v_rad)
    
    return v_deg, h_deg

def main():
    esp32 = connect_serial()
    print("=========================================")
    print(" ROBOTIC LAUNCHER - V1 CALIBRATION TOOL ")
    print(" Type 'quit' to exit.")
    print(" Coordinate System:")
    print("   X: Lateral (- Left / + Right) in meters")
    print("   Y: Forward Distance in meters")
    print("   Z: Target Height in meters")
    print("   V: Launch Velocity in km/h") # <-- Updated prompt
    print("=========================================\n")

    while True:
        try:
            user_input = input("Enter target (X Y Z V) separated by spaces: ")
            
            if user_input.strip().lower() in ['q', 'quit', 'exit']:
                print("Exiting...")
                break
                
            parts = user_input.split()
            if len(parts) != 4:
                print("[!] Please enter exactly 4 numbers: X Y Z V\n")
                continue
                
            x, y, z, v_kmh = map(float, parts)
            
            # --- THE CONVERSION ---
            # Convert km/h to m/s for physics calculations
            v_ms = v_kmh / 3.6
            
            # Calculate Angles
            v_deg, h_deg = calculate_kinematics(x, y, z, v_ms)
            
            if v_deg is None:
                continue # Skip if unreachable
                
            # Convert desired velocity (m/s) to RPM
            rpm = int(v_ms * VELOCITY_TO_RPM_MULTIPLIER)
            
            # Formulate ESP32 Command
            command = f"set {v_deg:.2f} {h_deg:.2f} {rpm} {rpm}\n"
            
            print(f"\n--- CALCULATION SUCCESS ---")
            print(f"Target Velocity      : {v_kmh} km/h ({v_ms:.2f} m/s)")
            print(f"Theoretical Tilt (v) : {v_deg:.2f} deg")
            print(f"Theoretical Pan (h)  : {h_deg:.2f} deg")
            print(f"Mapped Motor RPM     : {rpm}")
            print(f"Sending Command      : {command.strip()}")
            
            # Send to ESP32
            esp32.write(command.encode('utf-8'))
            
            # Read back response (Wait briefly for ESP32 to process)
            time.sleep(0.1)
            while esp32.in_waiting > 0:
                response = esp32.readline().decode('utf-8').strip()
                print(f"ESP32 Response       : {response}")
            print("---------------------------\n")

        except ValueError:
            print("[!] Invalid input. Please ensure you are entering numbers.\n")
        except KeyboardInterrupt:
            print("\nExiting...")
            break

    esp32.close()

if __name__ == "__main__":
    main()
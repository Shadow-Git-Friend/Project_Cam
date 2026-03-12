import cv2
import argparse

# 1. Настройка для чтения аргументов из командной строки
parser = argparse.ArgumentParser(description="Тестирование ID камеры.")
parser.add_argument("-i", "--id", type=int, required=True,
                    help="ID камеры для проверки (e.g., 0, 1, 2...).")
args = vars(parser.parse_args())

cam_id = args["id"]

print(f"[INFO] Попытка открыть камеру с ID: {cam_id}")

# 2. Попытка захвата
cap = cv2.VideoCapture(cam_id)

if not cap.isOpened():
    print(f"[ERROR] Не могу открыть камеру {cam_id}. Попробуйте другой ID.")
    exit()

# 3. Попытка установить высокое разрешение (для проверки)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

# 4. Чтение фактического разрешения
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

print(f"[INFO] Камера {cam_id} открыта. Фактическое разрешение: {width}x{height}")
print("[INFO] Нажмите 'q' для выхода и проверки следующего ID.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("[WARN] Не могу прочитать кадр.")
        break

    # Показываем ID на экране
    cv2.putText(frame, f"ID: {cam_id} | {width}x{height}", (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    cv2.imshow("Test Camera ID - Press 'q' to quit", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print(f"[INFO] Камера {cam_id} закрыта.")

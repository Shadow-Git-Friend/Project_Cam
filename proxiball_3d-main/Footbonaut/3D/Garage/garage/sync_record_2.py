import cv2
import time

ids = {
    "South": 0,
    "North": 2,
    "East" : 4,
    "West" : 6
}

W, H = 960, 960
FPS = 30

BACKEND = 0

caps = {}
writers = {}

for name, idx in ids.items():
    cap = cv2.VideoCapture(idx) if BACKEND == 0 else cv2.VideoCapture(idx, BACKEND)
    if not cap.isOpened():
        raise RuntimeError(f"fail opening {name} (index {idx})")
    
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FPS, FPS)

    ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    afps = cap.get(cv2.CAP_PROP_FPS)
    
    print(f"{name}: {aw}x{ah} @ {afps:.2f} fps (requested {W}x{H}@{FPS})")

    caps[name] = cap

fourcc = cv2.VideoWriter_fourcc(*'mp4v')

for name in caps.keys():
    writers[name] = cv2.VideoWriter(
        f"{name}.mp4",
        fourcc,
        afps,
        (W,H)
    )

print('ready')
time.sleep(2)

for cap in caps.values():
    for _ in range(5):
        cap.read()

start_time = time.time()

while True:
    frames = {}

    for cap in caps.values():
        cap.grab()
    
    for name, cap in caps.items():
        ret, frame = cap.retrieve()
        if not ret:
            print(f"fail {name}")
            break
        frames[name] = frame
    
    if len(frames) != 4:
        break
    
    for name in frames:
        writers[name].write(frames[name])

    cv2.imshow("south", frames["South"])

    if cv2.waitKey(1) & 0xFF == 27:
        break
    
for cap in caps.values():
    cap.release()

for writer in writers.values():
    writer.release()

cv2.destroyAllWindows()

print("done")
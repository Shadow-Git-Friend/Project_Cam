import cv2
import time

ids = {
    "South": 0,
    "North": 2,
    "East" : 4,
    "West" : 6
}

caps = {}
writers = {}

for name, idx in ids.items():
    cap = cv2.VideoCapture(idx)
    if not cap.isOpened():
        print('error opening')
        exit()
    caps[name] = cap

simple_cam = next(iter(caps.values()))
w = int(simple_cam.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(simple_cam.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = simple_cam.get(cv2.CAP_PROP_FPS)

if fps == 0:
    fps = 30

fourcc = cv2.VideoWriter_fourcc(*'mp4v')

for name in caps.keys():
    writers[name] = cv2.VideoWriter(
        f"{name}.mp4",
        fourcc,
        fps,
        (w,h)
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

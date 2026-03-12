#!/usr/bin/env python3
import cv2
import yaml
import time
import re
import numpy as np
from ultralytics import YOLO

model = YOLO("runs/detect/kz_ball_yolov11_kazakhstan/weights/best.pt")

with open("config/cameras.yaml") as f:
    cams = yaml.safe_load(f)["cameras"]

def get_id(s): 
    return int(re.search(r'\d+', str(s)).group())

print("\nДИАГНОСТИКА ТОЛЬКО В ТЕРМИНАЛЕ v5.0 — НИКАКИХ ОКОН")
print("Нажми Ctrl+C для выхода\n")
print("Cam1       Cam2       Cam3       Cam4")
print("-" * 50)

while True:
    line = ""
    for cam in cams:
        dev = get_id(cam["device"])
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 704)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 576)
        
        ret, frame = cap.read()
        cap.release()
        if not ret:
            line += " OFFLINE  "
            continue
            
        results = model(frame, conf=0.25, verbose=False)[0]
        boxes = results.boxes
        if boxes is not None and len(boxes) > 0:
            conf = boxes.conf.cpu().numpy().max()
            line += f" BALL {conf:.2f} "
        else:
            line += " NO BALL  "
    
    # Цветной вывод
    line = line.replace("BALL", "\033[92mBALL\033[0m")   # зелёный
    line = line.replace("NO BALL", "\033[91mNO BALL\033[0m") # красный
    line = line.replace("OFFLINE", "\033[93mOFFLINE\033[0m") # жёлтый
    
    print(f"\r{line}", end="", flush=True)
    time.sleep(0.8)

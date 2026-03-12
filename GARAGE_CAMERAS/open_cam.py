import cv2 as cv

idx = 6

# South = 0
# Norht = 2
# East = 4
# West = 6



cap = cv.VideoCapture(idx)

if not cap.isOpened():
    print('error opening')
    exit()

while True:
    ret, frame = cap.read()
    if not ret:
        print('error frame capture')
        break
    
    cv.imshow('camera', frame)

    if cv.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv.destroyAllWindows()
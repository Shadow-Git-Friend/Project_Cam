from roboflow import Roboflow

# authenticate
rf = Roboflow(api_key="aTij4FPzvwOBKP2MhC55")

# your workspace + project name
project = rf.workspace("azamat-fhvfo").project("footbonaut-6agev")

# your dataset version
version = project.version(6)

# download as YOLOv11 PyTorch format
dataset = version.download("yolov11")

# OpenCV Single Camera Test

Simple OpenCV script to open a camera and display FPS.

## Usage
```bash
python3 simple_cam.py [camera_index] [width height] [display_scale]
```

Examples:
```bash
python3 simple_cam.py 0
python3 simple_cam.py 2 1920 1080
python3 simple_cam.py 2 1920 1080 0.5
```

Press `q` to quit.

## 4-Camera 2x2 Grid
Display 4 cameras in a single window at full capture resolution, scaled for display.

```bash
python3 multi_cam_grid.py
python3 multi_cam_grid.py 0 2 4 6
python3 multi_cam_grid.py 0 2 4 6 --width 1920 --height 1080 --scale 0.4
python3 multi_cam_grid.py 0 2 4 6 --width 1920 --height 1080 --scale 0.4 --record-seconds 30
python3 multi_cam_grid.py 0 2 4 6 --width 1920 --height 1080 --scale 0.4 --grid-out recordings/grid_2x2.avi
```

Press `q` to quit.

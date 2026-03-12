# Simple Calibration Results

Generated using `simple_calibration.py` (No RANSAC filtering).

| Camera | Position (x, y, z) [m] | RMS Error (px) |
| :--- | :--- | :--- |
| **camNorth** | `[0.03, 1.13, 2.23]` | 39.9 |
| **camEast** | `[2.25, 0.21, 2.57]` | 50.0 |
| **camSouth** | `[6.14, 1.79, 2.27]` | 28.1 |
| **camWest** | `[2.93, 3.12, 2.29]` | 37.8 |

## Notes
These positions match the expected physical locations of the cameras relative to the origin (North-East corner).
The high RMS error is due to geometric inconsistencies in the map which are averaged out by this method to preserve global alignment.

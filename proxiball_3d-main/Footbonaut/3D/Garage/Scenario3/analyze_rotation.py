"""
Script to determine the rotation offset between measured corners and detector corners.
"""
import cv2
import numpy as np
import json

# Let's analyze a few specific tags from the debug image to determine rotation
# Floor tags (21, 22) appear upright, wall tags appear rotated

# From Dimensions.txt, let's check Tag ID=21 (floor tag)
# ID=21:
# c0(211.8, 182.5, 4)
# c1(211.8, 161, 4)   
# c2(233.3, 161, 4)
# c3(233.3, 182.5, 4)

# Let's see: c0 and c1 have same X (211.8), c2 and c3 have same X (233.3)
# c0 and c3 have same Y (182.5), c1 and c2 have same Y (161)
# So: c0-c1 is vertical edge (Y decreases), c0-c3 is horizontal edge (X increases)

# For tag on floor (Z=4), looking down:
# c0(211.8, 182.5) - higher Y (more West)
# c1(211.8, 161) - lower Y (more East)  
# c2(233.3, 161) - higher X (more South), lower Y
# c3(233.3, 182.5) - higher X, higher Y

# Pattern: c0 is NW, c1 is NE, c2 is SE, c3 is SW
# But detector expects: TL, TR, BR, BL when viewing from above
# When viewing floor from above (from +Z looking down):
# North is "top", South is "bottom", East is "left", West is "right"
# c0=NW would be "top-right", c1=NE would be "top-left", c2=SE would be "bottom-left", c3=SW would be "bottom-right"

# Wait, let me reconsider the coordinate system viewing direction.
# For a floor tag, cameras look DOWN at it.
# Coordinate system: X→S, Y→W, Z→Up
# For floor at Z=4:
#   When looking from above (camera POV), we see X-Y plane
#   X increases downward in image (North to South)
#   Y increases rightward in image (East to West)

# So for floor tags as measured:
# c0(211.8, 182.5) = medium X, high Y = appear as lower-right in camera
# c1(211.8, 161) = medium X, low Y = appear as lower-left in camera
# c2(233.3, 161) = high X, low Y = appear as upper-left in camera  
# c3(233.3, 182.5) = high X, high Y = appear as upper-right in camera

# But AprilTag detector returns TL, TR, BR, BL = c0, c1, c2, c3 (when tag is upright)
# So measured: [c0, c1, c2, c3] = [BR, BL, TL, TR] in camera view
# Need to reorder: detector [TL, TR, BR, BL] should map to measured [c2, c3, c0, c1]

print("Analysis suggests floor tags need rotation correction:")
print("Detector corners [0, 1, 2, 3] map to measured corners [c2, c3, c0, c1]")
print("\nFor wall tags, rotation will vary per tag placement orientation.")
print("\nWill need to determine rotation per tag or per wall.")

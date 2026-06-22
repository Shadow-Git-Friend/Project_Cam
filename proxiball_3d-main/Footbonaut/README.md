# Footbonaut 3D Ball Tracking System

## Overview
A high-precision, edge-optimized dual-camera 3D ball tracking system with real-time metric speed calculation, engineered specifically for close-proximity indoor training environments (Footbonaut). The core of this system is **Sport-YOLO v2**, a highly specialized vision engine designed to overcome the severe "ghost ball" motion blurs and micro-object latency issues where standard broadcast-trained models fail.

## Core Innovations: Sport-YOLO v2
Unlike generalized object detectors, the underlying model architecture (based originally on YOLO26's NMS-free design) has been heavily modified for high-speed edge tracking (e.g., NVIDIA Jetson):
- **Macro-Layer Elimination**: Standard P4/P5 layers are completely removed to prioritize ultra-fast, high-resolution feature maps at P2 (stride-4) and P3 (stride-8).
- **Hybrid Geometric Stem**: A dual-branch Stem combining fixed mathematical Gabor/LoG filters (for isotropic blob and texture detection) with empirical YOLO kernels, explicitly overcoming lighting and blur variations.
- **DCNv4 (Deformable Convolutions)**: Standard residual layers are replaced with PyTorch-native DCNv4, allowing the model's receptive field to dynamically "wrap" around elongated, motion-blurred footballs.
- **NWD (Normalized Wasserstein Distance) Loss**: Bounding boxes are supervised as 2D Gaussians, ensuring robust gradients even for sub-pixel object shifts where standard IoU completely collapses.

## Key Features

### 3D Tracking & System Architecture
- **Stereo Vision & Edge I/O**: Synchronized, asynchronous dual-camera streams processing via threaded queues (`stereo_inference.py`), eliminating I/O bottlenecks.
- **Kalman + 3D Kinematics**: The `Tracker3D` component calculates true metric velocity (m/s) and acceleration using Exponential Moving Average (EMA) smoothing and Kalman predictions.
- **Dynamic Anchoring**: High-precision Extrinsic/Intrinsic triangulation (`reconstruction.py`) using SVD and affine mapping, pushing physical coordinate localization to an RMSE < 0.1m on a 7.07m baseline.

### Adaptive Resource Management
- **Velocity-Based Frame Skipping**: The system dynamically skips heavy YOLO inference cycles if the physical ball moves at a high, predictable velocity—relying on Kalman estimations to boost system speeds to 100+ FPS.
- **Dynamic ROI**: Radically cuts down GFLOPs per frame by dynamically cropping the tensor input space based on preceding predictions.

### The ProxiBall Dataset
Instead of failing against standard broadcast datasets (like SoccerNet, ISSIA, or DFL) which lack the motion blur seen in extreme proximity bounds, this framework trained on a tightly filtered custom dataset—yielding a specialized **NWD-mAP of 0.9742**. During training (`train.py`), semantic-destroying augmentations like Mixup and Mosaic are purposely disabled to preserve micro-object invariants.

## Directory Structure
```
Footbonaut/
├── config/              # Configuration files (config.yaml)
├── docs/                # Various internal architecture and pipeline documentation
├── environments/        # Environment-specific calibration details and scenario states (e.g., Garage)
├── Paper/               # Technical methodologies and ablation studies detailing Sport-YOLO v2
├── tracker/             # Core 2D object matchers and the EMA metric Tracker3D
├── inference.py         # 2D single-camera tracking and trajectory evaluation 
├── reconstruction.py    # Stereo-calibrator (ChArUco/Kabsch algorithm) and 3D triangulator
├── stereo_inference.py  # The core hardware-aware 3D tracking engine handling multi-cam analytics
├── requirements.txt     # Requirements (Torch cu124, TensorRT 10.4.0)
├── train.py             # Custom training pipeline for the ProxiBall dataset
└── verify_engine.py     # End-to-end TensorRT `.engine` verifier
```

## Quick Start
1. **Prepare Environment**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Run 3D Dual-Camera Inference**:
   ```bash
   python3 stereo_inference.py --camA path/to/videoA.mp4 --camB path/to/videoB.mp4 --calib environments/Garage/Scenario3/calibration.npz --model model/sport_yolov2.engine
   ```
   *Output*: Annotations exported to `outputs/final_3d_view_*.mp4` alongside detailed analytic `.csv`/`.json` telemetry.

3. **Deploy & Validate TensorRT Engine**:
   ```bash
   python3 verify_engine.py
   ```

---
*Last Updated: March 2026*

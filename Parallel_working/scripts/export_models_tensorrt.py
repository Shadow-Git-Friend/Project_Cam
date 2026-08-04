#!/usr/bin/env python3
"""Export YOLO ball detector and RTMPose to ONNX / TensorRT engine files.

Usage:
    # Export YOLO ball model to TensorRT FP16:
    python Parallel_working/scripts/export_models_tensorrt.py \
        --yolo-model garage-20260217T113109Z-3-001/garage/y26s_v1_garage.pt \
        --yolo-format engine --yolo-half

    # Export RTMPose to ONNX (TensorRT via onnxruntime):
    python Parallel_working/scripts/export_models_tensorrt.py \
        --rtmpose-export --rtmpose-onnx-path Parallel_working/output/rtmpose_m.onnx

    # Benchmark existing models:
    python Parallel_working/scripts/export_models_tensorrt.py \
        --benchmark --yolo-model garage-20260217T113109Z-3-001/garage/y26s_v1_garage.pt

Requires: ultralytics, torch, onnx, onnxruntime-gpu (optional: tensorrt)
"""

import argparse
import time
import sys
from pathlib import Path

import numpy as np


def export_yolo(model_path, fmt="engine", half=True, imgsz=1280, device="cuda:0", batch=4):
    """Export YOLO model to TensorRT engine or ONNX.

    dynamic=True is mandatory (static engines segfault on batched multi-cam
    inference, see .claude/rules/perf.md). `batch` sets the optimization
    profile's max batch: 4 for the 4-cam rig, 6 for the 6-USB rig. Engines
    reject batches above this at runtime (setInputShape error), so match it
    to the camera count or chunk with --ball-max-batch/--pose-max-batch.
    """
    from ultralytics import YOLO

    model = YOLO(model_path)
    print(f"[YOLO] Exporting {model_path} to {fmt} (half={half}, imgsz={imgsz}, batch={batch})")
    export_path = model.export(
        format=fmt, half=half, imgsz=imgsz, device=device, dynamic=True, batch=int(batch)
    )
    print(f"[YOLO] Exported to: {export_path}")
    return export_path


def export_rtmpose_onnx(onnx_path, input_size=(192, 256)):
    """Export RTMPose-m to ONNX using MMPose's built-in export or torch.onnx.

    This uses mmdeploy if available, otherwise falls back to a manual approach.
    """
    onnx_path = Path(onnx_path)
    onnx_path.parent.mkdir(parents=True, exist_ok=True)

    # Try mmdeploy first (cleanest path)
    try:
        from mmdeploy.apis import torch2onnx
        from mmdeploy.backend.sdk.export_info import export2SDK

        deploy_cfg = "mmdeploy/configs/mmpose/pose-detection_onnxruntime_static.py"
        model_cfg = "mmpose/configs/body_2d_keypoint/rtmpose/coco/rtmpose-m_8xb256-420e_coco-256x192.py"

        torch2onnx(
            img=np.zeros((256, 192, 3), dtype=np.uint8),
            work_dir=str(onnx_path.parent),
            save_file=onnx_path.name,
            deploy_cfg=deploy_cfg,
            model_cfg=model_cfg,
            model_checkpoint="https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/rtmpose-m_simcc-ape210k-ft-coco_pt-aic-coco_420e-256x192-015a517c_20230126.pth",
            device="cuda:0",
        )
        print(f"[RTMPose] Exported via mmdeploy to: {onnx_path}")
        return str(onnx_path)
    except ImportError:
        print("[RTMPose] mmdeploy not found, trying manual torch.onnx export...")

    # Manual export via MMPose registry
    try:
        import torch
        from mmpose.apis import init_model

        # Download/load model config
        config = "rtmpose-m_8xb256-420e-coco-256x192"
        checkpoint_url = (
            "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/"
            "rtmpose-m_simcc-ape210k-ft-coco_pt-aic-coco_420e-256x192-015a517c_20230126.pth"
        )

        # Try to initialize from MMPose model zoo
        try:
            from mmpose.apis import MMPoseInferencer
            inferencer = MMPoseInferencer(
                pose2d="rtmpose-m_8xb256-420e-coco-256x192",
                device="cuda:0",
            )
            model = inferencer.pose_estimator
        except Exception:
            print("[RTMPose] Could not load model via MMPoseInferencer.")
            print("[RTMPose] Please install mmdeploy for clean ONNX export:")
            print("  pip install mmdeploy mmdeploy-runtime-gpu")
            return None

        model.eval()
        dummy_input = torch.randn(1, 3, input_size[1], input_size[0], device="cuda:0")

        torch.onnx.export(
            model.backbone,
            dummy_input,
            str(onnx_path),
            input_names=["input"],
            output_names=["output"],
            opset_version=13,
            dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
        )
        print(f"[RTMPose] Backbone exported to: {onnx_path}")
        print("[RTMPose] NOTE: Full model export (backbone + head) requires mmdeploy.")
        return str(onnx_path)

    except Exception as e:
        print(f"[RTMPose] Export failed: {e}")
        print("[RTMPose] Recommended: install mmdeploy for reliable ONNX export")
        return None


def benchmark_yolo(model_path, device="cuda:0", n_warmup=10, n_iter=50):
    """Benchmark YOLO inference latency."""
    from ultralytics import YOLO
    import torch

    model = YOLO(model_path)
    dummy = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)

    print(f"[Bench YOLO] Warming up {n_warmup} iterations...")
    for _ in range(n_warmup):
        model(dummy, device=device, verbose=False)

    if torch.cuda.is_available():
        torch.cuda.synchronize()

    times = []
    for _ in range(n_iter):
        t0 = time.perf_counter()
        model(dummy, device=device, verbose=False)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        times.append((time.perf_counter() - t0) * 1000)

    times = np.array(times)
    print(f"[Bench YOLO] {model_path}")
    print(f"  Mean: {times.mean():.1f} ms | Median: {np.median(times):.1f} ms | "
          f"P95: {np.percentile(times, 95):.1f} ms | P5: {np.percentile(times, 5):.1f} ms")
    return times


def benchmark_mmpose(device="cuda:0", n_warmup=5, n_iter=20):
    """Benchmark MMPose inference latency."""
    try:
        from mmpose.apis import MMPoseInferencer
    except ImportError:
        print("[Bench MMPose] mmpose not installed, skipping.")
        return None

    dummy = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)

    try:
        pose_infer = MMPoseInferencer(
            pose2d="rtmpose-m_8xb256-420e-coco-256x192",
            det_model="rtmdet-m",
            device=device,
        )
    except Exception:
        pose_infer = MMPoseInferencer(pose2d="human", device=device)

    print(f"[Bench MMPose] Warming up {n_warmup} iterations...")
    for _ in range(n_warmup):
        list(pose_infer(dummy, return_vis=False))

    import torch
    if torch.cuda.is_available():
        torch.cuda.synchronize()

    times = []
    for _ in range(n_iter):
        t0 = time.perf_counter()
        list(pose_infer(dummy, return_vis=False))
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        times.append((time.perf_counter() - t0) * 1000)

    times = np.array(times)
    print(f"[Bench MMPose] RTMPose-m + RTMDet-m")
    print(f"  Mean: {times.mean():.1f} ms | Median: {np.median(times):.1f} ms | "
          f"P95: {np.percentile(times, 95):.1f} ms | P5: {np.percentile(times, 5):.1f} ms")
    return times


def benchmark_onnx_pose(onnx_path, device="cuda", n_warmup=10, n_iter=50):
    """Benchmark ONNX Runtime pose inference."""
    try:
        import onnxruntime as ort
    except ImportError:
        print("[Bench ONNX] onnxruntime not installed. Install with:")
        print("  pip install onnxruntime-gpu")
        return None

    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if device == "cuda" else ["CPUExecutionProvider"]
    session = ort.InferenceSession(str(onnx_path), providers=providers)
    input_name = session.get_inputs()[0].name
    input_shape = session.get_inputs()[0].shape
    print(f"[Bench ONNX] Input: {input_name} shape={input_shape}")

    # Build dummy input matching expected shape
    shape = [s if isinstance(s, int) else 1 for s in input_shape]
    dummy = np.random.randn(*shape).astype(np.float32)

    print(f"[Bench ONNX] Warming up {n_warmup} iterations...")
    for _ in range(n_warmup):
        session.run(None, {input_name: dummy})

    times = []
    for _ in range(n_iter):
        t0 = time.perf_counter()
        session.run(None, {input_name: dummy})
        times.append((time.perf_counter() - t0) * 1000)

    times = np.array(times)
    print(f"[Bench ONNX] {onnx_path}")
    print(f"  Mean: {times.mean():.1f} ms | Median: {np.median(times):.1f} ms | "
          f"P95: {np.percentile(times, 95):.1f} ms | P5: {np.percentile(times, 5):.1f} ms")
    return times


def main():
    ap = argparse.ArgumentParser(description="Export and benchmark models for TensorRT/ONNX acceleration.")

    # YOLO export
    ap.add_argument("--yolo-model", default="", help="Path to YOLO .pt model")
    ap.add_argument("--yolo-format", default="engine", choices=["engine", "onnx", "torchscript"],
                    help="Export format for YOLO")
    ap.add_argument("--yolo-half", action="store_true", help="FP16 quantization for YOLO export")
    ap.add_argument("--yolo-imgsz", type=int, default=1280, help="Input image size for YOLO export")
    ap.add_argument("--yolo-batch", type=int, default=4,
                    help="Max batch in the TRT optimization profile (4 = 4-cam rig, 6 = 6-USB rig).")

    # RTMPose export
    ap.add_argument("--rtmpose-export", action="store_true", help="Export RTMPose to ONNX")
    ap.add_argument("--rtmpose-onnx-path", default="Parallel_working/output/rtmpose_m.onnx",
                    help="Output path for RTMPose ONNX model")

    # Benchmark
    ap.add_argument("--benchmark", action="store_true", help="Run inference benchmarks")
    ap.add_argument("--bench-onnx-path", default="", help="ONNX model path for benchmark")
    ap.add_argument("--device", default="cuda:0", help="Device for export/benchmark")

    args = ap.parse_args()

    if not any([args.yolo_model, args.rtmpose_export, args.benchmark]):
        ap.print_help()
        sys.exit(1)

    # YOLO export
    if args.yolo_model and not args.benchmark:
        export_yolo(args.yolo_model, fmt=args.yolo_format, half=args.yolo_half,
                    imgsz=args.yolo_imgsz, device=args.device, batch=args.yolo_batch)

    # RTMPose export
    if args.rtmpose_export:
        export_rtmpose_onnx(args.rtmpose_onnx_path)

    # Benchmarks
    if args.benchmark:
        print("=" * 60)
        print("MODEL BENCHMARK SUITE")
        print("=" * 60)

        if args.yolo_model:
            print("\n--- YOLO Ball Detector ---")
            benchmark_yolo(args.yolo_model, device=args.device)

        print("\n--- MMPose (RTMPose-m + RTMDet-m) ---")
        benchmark_mmpose(device=args.device)

        if args.bench_onnx_path:
            print("\n--- ONNX Runtime Pose ---")
            benchmark_onnx_pose(args.bench_onnx_path, device="cuda")

        # Also export and benchmark YOLO TensorRT if model given
        if args.yolo_model:
            pt_path = Path(args.yolo_model)
            engine_path = pt_path.with_suffix(".engine")
            if not engine_path.exists():
                print("\n--- Exporting YOLO to TensorRT FP16 ---")
                export_yolo(args.yolo_model, fmt="engine", half=True,
                            imgsz=args.yolo_imgsz, device=args.device)
            if engine_path.exists():
                print("\n--- YOLO TensorRT Engine ---")
                benchmark_yolo(str(engine_path), device=args.device)


if __name__ == "__main__":
    main()

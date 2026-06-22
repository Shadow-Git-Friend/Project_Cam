"""
garage_export_engine.py
Export y26s_garagev2.pt -> ONNX -> TensorRT FP16 engine.
Run from Footbonaut root:
    python Garage/garage_export_engine.py
"""
import os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # Footbonaut/
MODEL_PT   = ROOT / "model" / "y26s_garagev2.pt"
MODEL_ONNX = ROOT / "model" / "y26s_garagev2.onnx"
MODEL_ENG  = ROOT / "model" / "y26s_garagev2.engine"

IMGSZ   = 960   # must match config.yaml
OPSET   = 17
MIN_B   = 1
OPT_B   = 4     # optimised for batch=4 (one frame per camera)
MAX_B   = 8


# ── Step 1: Export to ONNX via Ultralytics ──────────────────────────────────
def export_onnx():
    if MODEL_ONNX.exists():
        print(f"[ONNX] Already exists: {MODEL_ONNX} – skipping export.")
        return
    from ultralytics import YOLO
    print(f"[ONNX] Loading {MODEL_PT} ...")
    model = YOLO(str(MODEL_PT))
    print(f"[ONNX] Exporting to ONNX (imgsz={IMGSZ}, dynamic=True, opset={OPSET}) ...")
    path = model.export(format="onnx", imgsz=IMGSZ, dynamic=True, opset=OPSET)
    # Ultralytics saves alongside the .pt; copy/rename if needed
    expected = MODEL_PT.with_suffix(".onnx")
    if expected.exists() and expected != MODEL_ONNX:
        import shutil
        shutil.move(str(expected), str(MODEL_ONNX))
    print(f"[ONNX] Saved: {MODEL_ONNX}  ({MODEL_ONNX.stat().st_size/1e6:.1f} MB)")


# ── Step 2: Build TensorRT engine ───────────────────────────────────────────
def build_engine():
    if MODEL_ENG.exists():
        print(f"[TRT]  Already exists: {MODEL_ENG} – skipping build.")
        return
    try:
        import tensorrt as trt
    except ImportError:
        print("[TRT]  tensorrt not found; falling back to Ultralytics TRT export.")
        _build_via_ultralytics()
        return

    TRT_LOGGER = trt.Logger(trt.Logger.INFO)
    print(f"[TRT]  Building engine from {MODEL_ONNX} ...")
    t0 = time.perf_counter()

    builder  = trt.Builder(TRT_LOGGER)
    network  = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser   = trt.OnnxParser(network, TRT_LOGGER)
    config   = builder.create_builder_config()

    # Parse ONNX
    with open(str(MODEL_ONNX), "rb") as f:
        if not parser.parse(f.read()):
            for i in range(parser.num_errors):
                print("  ERROR:", parser.get_error(i))
            raise RuntimeError("ONNX parse failed.")

    # FP16
    if builder.platform_has_fast_fp16:
        print("[TRT]  FP16 enabled.")
        config.set_flag(trt.BuilderFlag.FP16)

    # Optimization profile
    profile    = builder.create_optimization_profile()
    inp_tensor = network.get_input(0)
    inp_name   = inp_tensor.name
    print(f"[TRT]  Input tensor: '{inp_name}' shape={inp_tensor.shape}")

    profile.set_shape(inp_name,
                      (MIN_B, 3, IMGSZ, IMGSZ),
                      (OPT_B, 3, IMGSZ, IMGSZ),
                      (MAX_B, 3, IMGSZ, IMGSZ))
    config.add_optimization_profile(profile)

    serialized = builder.build_serialized_network(network, config)
    if serialized is None:
        raise RuntimeError("Engine build failed.")

    MODEL_ENG.write_bytes(serialized)
    elapsed = time.perf_counter() - t0
    print(f"[TRT]  Engine saved: {MODEL_ENG}  ({MODEL_ENG.stat().st_size/1e6:.1f} MB)  [{elapsed:.0f}s]")


def _build_via_ultralytics():
    """Fallback: use Ultralytics built-in TRT export."""
    from ultralytics import YOLO
    model = YOLO(str(MODEL_PT))
    path = model.export(format="engine", imgsz=IMGSZ, dynamic=True, half=True)
    expected = MODEL_PT.with_suffix(".engine")
    if expected.exists() and expected != MODEL_ENG:
        import shutil
        shutil.move(str(expected), str(MODEL_ENG))
    print(f"[TRT]  Engine saved (via Ultralytics): {MODEL_ENG}")


if __name__ == "__main__":
    export_onnx()
    build_engine()
    print("\n✓ Done. Engine ready at:", MODEL_ENG)

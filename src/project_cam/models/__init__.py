"""Model registry and provenance helpers.

This package deliberately does not import model runtimes such as Ultralytics or
TensorRT. It records artifact metadata and checksums so model lifecycle state can
be tested in CI without a GPU.
"""

from .registry import ModelRecord, ModelRegistry, load_model_registry, sha256_file

__all__ = [
    "ModelRecord",
    "ModelRegistry",
    "load_model_registry",
    "sha256_file",
]

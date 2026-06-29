"""Production service layer for Project_Cam.

A thin, aim-only HTTP surface over the hardware-free core: camera profiles,
multi-view triangulation, Kalman prediction, session reports, health, and
Prometheus metrics. It deliberately reuses ``project_cam.geometry`` and never
copies geometry code, and it can never actuate the launcher -- BLM firing stays
in the safety-gated launcher runtime only (see docs/safety_boundaries.md).

The modules split by dependency so the core stays importable on a minimal env:

- ``pipeline_adapter`` -- pure Python (numpy + PyYAML); profile loading + geometry.
- ``service``          -- business logic returning plain dicts; raises ServiceError.
- ``schemas``          -- pydantic request/response models (optional dependency).
"""

# Defined before the submodule imports below: service.py does
# ``from . import API_VERSION`` during package initialization.
API_VERSION = "0.1.0"

from .pipeline_adapter import (  # noqa: E402
    CameraProfile,
    list_profiles,
    load_camera_profile,
    run_kalman_track,
    triangulate_observations,
)
from .service import ServiceError  # noqa: E402

__all__ = [
    "CameraProfile",
    "list_profiles",
    "load_camera_profile",
    "triangulate_observations",
    "run_kalman_track",
    "ServiceError",
    "API_VERSION",
]

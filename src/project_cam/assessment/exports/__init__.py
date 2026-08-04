"""Standards exports for Project_Cam assessment recordings.

C3D (biomechanics) is currently implemented. TRC and BVH are planned for a
follow-up; their absence is intentional, see docs/roadmap if you need them.
"""

from .c3d_writer import write_c3d

__all__ = ["write_c3d"]

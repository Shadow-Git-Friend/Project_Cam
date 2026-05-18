"""Rep-counting state machine for live push-up / squat training.

Pure logic at this layer; no I/O, no OpenCV, no UDP.
"""

from .rep_state import CounterConfig, RepCounter, RepState, make_counter

__all__ = ["CounterConfig", "RepCounter", "RepState", "make_counter"]

"""Live push-up / squat trainer: UDP-driven OpenCV coaching dashboard."""

from .rep_state import CounterConfig, RepCounter, RepState, make_counter

__all__ = ["CounterConfig", "RepCounter", "RepState", "make_counter"]

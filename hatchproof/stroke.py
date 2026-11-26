"""Domain-name alias for the stroke width geometry."""

from .width import *  # noqa: F401,F403
from .width import measure_stroke_width, measure_width, stroke_width, width_report, width_settings

__all__ = ["measure_stroke_width", "measure_width", "stroke_width", "width_report", "width_settings"]

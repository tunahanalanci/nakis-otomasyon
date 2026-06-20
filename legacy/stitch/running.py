"""Running-stitch generator for outlines and arbitrary line strings."""

from __future__ import annotations

import numpy as np
from shapely.geometry import LineString, Polygon

from src.config import Config


def generate_outline(polygon: Polygon, cfg: Config) -> list[tuple[float, float]]:
    """Sample the exterior ring of *polygon* with evenly spaced running stitches.

    Does not close the loop: the generated sequence starts and ends at the
    same ring vertex but does not duplicate that point.
    """
    return generate_line(LineString(polygon.exterior.coords), cfg.min_stitch_mm)


def generate_line(line: LineString, spacing_mm: float) -> list[tuple[float, float]]:
    """Place stitches along *line* at *spacing_mm* intervals.

    Both endpoints are included.  The number of intervals is
    ``max(1, round(length / spacing_mm))`` so the actual spacing may differ
    slightly from the requested value to reach the end exactly.
    """
    length = line.length
    if length < 1e-9 or spacing_mm < 1e-9:
        return []
    n = max(1, round(length / spacing_mm))
    return [
        (line.interpolate(t).x, line.interpolate(t).y)
        for t in np.linspace(0.0, length, n + 1)
    ]

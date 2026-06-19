"""Tatami / fill-stitch generator for closed polygons."""

from __future__ import annotations

from shapely.geometry import Polygon

from src.config import FillConfig


def generate(polygon: Polygon, cfg: FillConfig) -> list[tuple[float, float]]:
    """Generate fill-stitch coordinates for *polygon*.

    Returns a flat list of (x_mm, y_mm) stitch points in sewing order.

    TODO: compute parallel scan lines at cfg.angle_deg across the bounding box.
    TODO: clip each scan line to the polygon interior using Shapely intersection.
    TODO: alternate row direction for back-and-forth (boustrophedon) travel.
    TODO: apply cfg.spacing_mm between rows.
    TODO: add pull-compensation offset to each scan line endpoint.
    TODO: call underlay.generate() when cfg.underlay is True and prepend stitches.
    """
    raise NotImplementedError

"""Satin-stitch generator for narrow elongated shapes (borders, letters)."""

from __future__ import annotations

from shapely.geometry import Polygon

from src.config import SatinConfig


def generate(polygon: Polygon, cfg: SatinConfig) -> list[tuple[float, float]]:
    """Generate satin-stitch coordinates for *polygon*.

    Satin is used when the polygon width is between cfg.min_width_mm and
    cfg.max_width_mm; outside that range, fall back to fill or running stitch.

    TODO: compute the polygon's medial axis (Voronoi-based or chordal).
    TODO: generate paired stitch points on opposite edges along the medial axis.
    TODO: apply cfg.density_mm spacing along the axis.
    TODO: add a zig-zag underlay pass before the top satin pass.
    """
    raise NotImplementedError


def width_at(polygon: Polygon) -> float:
    """Estimate the average width of *polygon* in mm.

    TODO: use minimum bounding rectangle or medial-axis approach.
    """
    raise NotImplementedError

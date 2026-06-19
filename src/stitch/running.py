"""Running-stitch generator for outlines and very thin shapes."""

from __future__ import annotations

from shapely.geometry import LineString, Polygon

from src.config import Config


def generate_outline(polygon: Polygon, cfg: Config) -> list[tuple[float, float]]:
    """Walk the exterior ring of *polygon* with evenly spaced running stitches.

    TODO: sample the exterior at cfg.min_stitch_mm intervals using Shapely interpolate.
    TODO: optionally triple-stitch (forward-back-forward) for reinforced outlines.
    """
    raise NotImplementedError


def generate_line(line: LineString, spacing_mm: float) -> list[tuple[float, float]]:
    """Place stitches along an arbitrary *line* at *spacing_mm* intervals.

    TODO: use line.interpolate(distance) for uniform spacing.
    """
    raise NotImplementedError

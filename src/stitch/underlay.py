"""Underlay-stitch generator: stabilises fabric before the top layer."""

from __future__ import annotations

from shapely.geometry import Polygon

from src.config import FillConfig


def generate(polygon: Polygon, cfg: FillConfig) -> list[tuple[float, float]]:
    """Generate underlay stitches for *polygon*.

    Underlay runs at 90° offset from the fill angle and at 2–3× the fill spacing
    to anchor the fabric without showing through the top layer.

    TODO: compute underlay angle as (cfg.angle_deg + 90) % 180.
    TODO: use 2.5 * cfg.spacing_mm for underlay row spacing.
    TODO: reuse fill.generate() internals with overridden angle/spacing parameters.
    """
    raise NotImplementedError

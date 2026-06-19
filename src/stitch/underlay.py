"""Underlay-stitch generator: stabilises fabric before the top fill layer."""

from __future__ import annotations

from shapely.geometry import LineString, Polygon

from src.config import FillConfig

# Underlay uses sparser spacing than the top fill to anchor without showing through
_OUTLINE_SPACING_FACTOR: float = 5.0   # outline spacing = fill spacing × this
_ZIGZAG_SPACING_FACTOR:  float = 2.5   # zigzag row spacing = fill spacing × this
_ZIGZAG_STITCH_FACTOR:   float = 5.0   # zigzag stitch length = fill spacing × this


def generate(polygon: Polygon, cfg: FillConfig) -> list[tuple[float, float]]:
    """Generate a two-pass underlay for *polygon*:

    Pass 1 — Sparse running-stitch outline (spacing = cfg.spacing_mm × 5).
    Pass 2 — Coarse tatami fill at 90° to the main fill angle
              (row spacing = cfg.spacing_mm × 2.5, no nested underlay).

    Imports from :mod:`src.stitch.fill` and :mod:`src.stitch.running` are
    deferred inside the function body to break the fill ↔ underlay import cycle.
    """
    if polygon.is_empty:
        return []

    pts: list[tuple[float, float]] = []
    outline_spacing = cfg.spacing_mm * _OUTLINE_SPACING_FACTOR

    # ── Pass 1: sparse edge-walk ──────────────────────────────────────────────
    from src.stitch.running import generate_line  # noqa: PLC0415
    pts.extend(generate_line(LineString(polygon.exterior.coords), outline_spacing))

    # ── Pass 2: coarse perpendicular fill ─────────────────────────────────────
    from src.stitch.fill import generate as _fill  # noqa: PLC0415

    underlay_cfg = FillConfig(
        spacing_mm=cfg.spacing_mm * _ZIGZAG_SPACING_FACTOR,
        angle_deg=(cfg.angle_deg + 90.0) % 180.0,
        underlay=False,  # prevent recursion
    )
    pts.extend(_fill(
        polygon,
        underlay_cfg,
        stitch_mm=cfg.spacing_mm * _ZIGZAG_STITCH_FACTOR,
    ))

    return pts

"""Tatami / fill-stitch generator for closed polygons."""

from __future__ import annotations

import math

import numpy as np
from shapely.affinity import rotate as _shp_rotate
from shapely.affinity import scale as _shp_scale
from shapely.geometry import GeometryCollection, LineString, MultiLineString, Polygon

from src.config import FillConfig

_STITCH_MM_DEFAULT: float = 3.0


def generate(
    polygon: Polygon,
    cfg: FillConfig,
    stitch_mm: float = _STITCH_MM_DEFAULT,
    pull_compensation_mm: float = 0.0,
) -> list[tuple[float, float]]:
    """Generate fill-stitch coordinates for *polygon* in mm.

    Returns a flat list of (x_mm, y_mm) points in boustrophedon sewing order.

    Parameters
    ----------
    polygon              : Shapely Polygon in mm (may contain holes).
    cfg                  : FillConfig — spacing_mm, angle_deg, underlay flag.
    stitch_mm            : target stitch length along each scan-line segment.
    pull_compensation_mm : expand polygon perpendicular to fill direction by
                           this amount on each side before computing scan lines.
    """
    if polygon.is_empty or not polygon.is_valid:
        return []

    pts: list[tuple[float, float]] = []

    # Prepend underlay (lazy import breaks the fill ↔ underlay cycle)
    if cfg.underlay:
        from src.stitch.underlay import generate as _underlay  # noqa: PLC0415
        pts.extend(_underlay(polygon, cfg))

    # Apply pull compensation in place so expansion is absorbed into scan lines
    working = _apply_pull_compensation(polygon, pull_compensation_mm, cfg.angle_deg)

    cx, cy = working.centroid.x, working.centroid.y
    rotated = _shp_rotate(working, -cfg.angle_deg, origin=(cx, cy))

    minx, miny, maxx, maxy = rotated.bounds

    # Start half a step inside the bounds so scan lines never sit exactly on
    # the polygon boundary (avoids collinear boundary-edge intersections that
    # inflate segment counts near holes).
    ys = np.arange(miny + cfg.spacing_mm * 0.5, maxy, cfg.spacing_mm)

    all_rotated: list[tuple[float, float]] = []

    for row_idx, y in enumerate(ys):
        scan = LineString([(minx - 1.0, y), (maxx + 1.0, y)])
        segs = _extract_segs(rotated.intersection(scan))
        if not segs:
            continue

        # Normalize each segment to go left-to-right (Shapely does not
        # guarantee direction on intersection results).
        segs = [_normalize_seg(s) for s in segs]
        segs.sort(key=lambda s: s.coords[0][0])

        row_pts: list[tuple[float, float]] = []
        for seg in segs:
            row_pts.extend(_sample_segment(seg, stitch_mm))

        # Boustrophedon: odd rows travel right-to-left
        if row_idx % 2 == 1:
            row_pts = row_pts[::-1]

        all_rotated.extend(row_pts)

    pts.extend(_rotate_pts(all_rotated, cfg.angle_deg, cx, cy))
    return pts


# ── Pull compensation ─────────────────────────────────────────────────────────

def apply_pull_compensation(
    polygon: Polygon,
    compensation_mm: float,
    angle_deg: float,
) -> Polygon:
    """Expand *polygon* by *compensation_mm* on each side perpendicular to *angle_deg*.

    Rotates the polygon so the fill direction is horizontal, scales in y
    (the perpendicular axis), then rotates back.
    """
    return _apply_pull_compensation(polygon, compensation_mm, angle_deg)


# ── Private helpers ────────────────────────────────────────────────────────────

def _apply_pull_compensation(
    polygon: Polygon,
    compensation_mm: float,
    angle_deg: float,
) -> Polygon:
    if compensation_mm <= 0.0:
        return polygon
    origin = (polygon.centroid.x, polygon.centroid.y)
    rotated = _shp_rotate(polygon, -angle_deg, origin=origin)
    _, miny, _, maxy = rotated.bounds
    height = maxy - miny
    if height < 1e-9:
        return polygon
    yfact = (height + 2.0 * compensation_mm) / height
    expanded = _shp_scale(rotated, xfact=1.0, yfact=yfact, origin=origin)
    return _shp_rotate(expanded, angle_deg, origin=origin)


def _normalize_seg(seg: LineString) -> LineString:
    """Ensure *seg* runs left-to-right (ties broken by bottom-to-top).

    Shapely does not guarantee the direction of intersection results, so we
    normalise before boustrophedon reversal to get deterministic ordering.
    """
    c = seg.coords
    if c[0][0] > c[-1][0] or (c[0][0] == c[-1][0] and c[0][1] > c[-1][1]):
        return LineString(list(c)[::-1])
    return seg


def _extract_segs(intersection) -> list[LineString]:
    """Recursively collect non-degenerate LineString segments from *intersection*."""
    if intersection is None or intersection.is_empty:
        return []
    if isinstance(intersection, LineString):
        return [intersection] if intersection.length > 1e-9 else []
    if isinstance(intersection, MultiLineString):
        return [g for g in intersection.geoms if g.length > 1e-9]
    if isinstance(intersection, GeometryCollection):
        result: list[LineString] = []
        for g in intersection.geoms:
            result.extend(_extract_segs(g))
        return result
    return []


def _sample_segment(
    line: LineString,
    stitch_mm: float,
) -> list[tuple[float, float]]:
    """Sample *line* at *stitch_mm* intervals, including both endpoints."""
    length = line.length
    if length < 1e-9:
        return []
    n = max(1, round(length / stitch_mm))
    return [
        (line.interpolate(t).x, line.interpolate(t).y)
        for t in np.linspace(0.0, length, n + 1)
    ]


def _rotate_pts(
    pts: list[tuple[float, float]],
    angle_deg: float,
    cx: float,
    cy: float,
) -> list[tuple[float, float]]:
    """Rotate every point in *pts* by *angle_deg* degrees about (*cx*, *cy*)."""
    if not pts:
        return []
    arr = np.asarray(pts, dtype=float)
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    dx, dy = arr[:, 0] - cx, arr[:, 1] - cy
    return list(zip(
        (cx + dx * cos_a - dy * sin_a).tolist(),
        (cy + dx * sin_a + dy * cos_a).tolist(),
    ))

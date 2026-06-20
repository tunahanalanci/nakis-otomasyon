"""Satin-stitch generator for narrow elongated shapes."""

from __future__ import annotations

import math

import numpy as np
from shapely.affinity import rotate as _shp_rotate
from shapely.geometry import LineString, MultiLineString, Polygon

from src.config import SatinConfig


def generate(polygon: Polygon, cfg: SatinConfig) -> list[tuple[float, float]]:
    """Generate satin-stitch coordinates for *polygon*.

    Stitches span the full short dimension of the shape (perpendicular to the
    long axis) at cfg.density_mm intervals along the long axis.  No stitch
    subdivision: each scan-line intersection becomes a single stitch pair.

    Returns an empty list if the shape width is outside
    [cfg.min_width_mm, cfg.max_width_mm].  The caller should fall back to fill
    or running stitch in those cases.
    """
    if polygon.is_empty or not polygon.is_valid:
        return []

    w = width_at(polygon)
    if w < cfg.min_width_mm or w > cfg.max_width_mm:
        return []

    # Rotate so that stitches become horizontal scans:
    # long axis is at mbr_angle → stitches are at mbr_angle+90 → rotate by -(mbr_angle+90)
    mbr_angle = _mbr_long_axis_angle(polygon)
    cx, cy = polygon.centroid.x, polygon.centroid.y
    rotated = _shp_rotate(polygon, -(mbr_angle + 90.0), origin=(cx, cy))

    minx, miny, maxx, maxy = rotated.bounds
    ys = np.arange(miny, maxy + cfg.density_mm * 0.5, cfg.density_mm)

    all_rotated: list[tuple[float, float]] = []

    for row_idx, y in enumerate(ys):
        scan = LineString([(minx - 1.0, y), (maxx + 1.0, y)])
        seg = _longest_seg(rotated.intersection(scan))
        if seg is None:
            continue

        p0 = (seg.coords[0][0], seg.coords[0][1])
        p1 = (seg.coords[-1][0], seg.coords[-1][1])

        # Zigzag: alternate which edge is visited first
        if row_idx % 2 == 0:
            all_rotated.extend([p0, p1])
        else:
            all_rotated.extend([p1, p0])

    return _rotate_pts(all_rotated, mbr_angle + 90.0, cx, cy)


def width_at(polygon: Polygon) -> float:
    """Return the shorter MBR dimension of *polygon* in mm (≈ shape width)."""
    mbr    = polygon.minimum_rotated_rectangle
    coords = list(mbr.exterior.coords)
    l0 = math.hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
    l1 = math.hypot(coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])
    return min(l0, l1)


# ── Private helpers ────────────────────────────────────────────────────────────

def _mbr_long_axis_angle(polygon: Polygon) -> float:
    """Return the angle (0–180°) of the long axis of the minimum bounding rectangle."""
    mbr    = polygon.minimum_rotated_rectangle
    coords = list(mbr.exterior.coords)
    dx0, dy0 = coords[1][0] - coords[0][0], coords[1][1] - coords[0][1]
    dx1, dy1 = coords[2][0] - coords[1][0], coords[2][1] - coords[1][1]
    l0, l1   = math.hypot(dx0, dy0), math.hypot(dx1, dy1)
    if l0 >= l1:
        return math.degrees(math.atan2(dy0, dx0)) % 180.0
    return math.degrees(math.atan2(dy1, dx1)) % 180.0


def _longest_seg(intersection) -> LineString | None:
    """Return the longest non-degenerate LineString from *intersection*, or None."""
    if intersection is None or intersection.is_empty:
        return None
    if isinstance(intersection, LineString) and intersection.length > 1e-9:
        return intersection
    if isinstance(intersection, MultiLineString):
        segs = [g for g in intersection.geoms if g.length > 1e-9]
        return max(segs, key=lambda s: s.length) if segs else None
    return None


def _rotate_pts(
    pts: list[tuple[float, float]],
    angle_deg: float,
    cx: float,
    cy: float,
) -> list[tuple[float, float]]:
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

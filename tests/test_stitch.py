"""Tests for src/stitch/ modules (fill, satin, running, underlay)."""

from __future__ import annotations

import math

import pytest
from shapely.affinity import rotate as shp_rotate
from shapely.geometry import LineString, Polygon

from src.config import Config, FillConfig, SatinConfig


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def _square(side: float = 10.0, origin: tuple = (0.0, 0.0)) -> Polygon:
    x0, y0 = origin
    return Polygon([
        (x0,        y0),
        (x0 + side, y0),
        (x0 + side, y0 + side),
        (x0,        y0 + side),
    ])


def _rect(w: float, h: float) -> Polygon:
    return Polygon([(0, 0), (w, 0), (w, h), (0, h)])


def _donut(outer: float = 10.0, inner: float = 4.0) -> Polygon:
    cx, cy = outer / 2, outer / 2
    half = inner / 2
    return Polygon(
        [(0, 0), (outer, 0), (outer, outer), (0, outer)],
        [[(cx - half, cy - half), (cx + half, cy - half),
          (cx + half, cy + half), (cx - half, cy + half)]],
    )


# ══════════════════════════════════════════════════════════════════════════════
# fill.py
# ══════════════════════════════════════════════════════════════════════════════

class TestFillGenerate:
    """Core fill-stitch generation tests."""

    def test_count_inversely_proportional_to_spacing(self):
        """Halving spacing_mm must approximately double the stitch count."""
        from src.stitch.fill import generate

        sq   = _square(10.0)
        coarse = FillConfig(spacing_mm=1.0, angle_deg=0.0, underlay=False)
        fine   = FillConfig(spacing_mm=0.5, angle_deg=0.0, underlay=False)

        n_coarse = len(generate(sq, coarse, stitch_mm=3.0))
        n_fine   = len(generate(sq, fine,   stitch_mm=3.0))

        assert n_coarse > 0
        ratio = n_fine / n_coarse
        assert 1.7 <= ratio <= 2.3, f"expected ~2x, got {ratio:.2f}"

    def test_holes_excluded_from_stitches(self):
        """No stitch must land strictly inside the polygon hole."""
        from src.stitch.fill import generate

        outer  = 10.0
        inner  = 4.0          # hole: 3 < x < 7, 3 < y < 7
        donut  = _donut(outer, inner)
        solid  = _square(outer)
        cfg    = FillConfig(spacing_mm=0.5, angle_deg=0.0, underlay=False)

        # stitch_mm=1.0 gives 11 pts/row for the full 10 mm line vs 4+4=8 pts
        # per hole-row, so donut reliably has fewer total points than solid.
        pts_donut = generate(donut, cfg, stitch_mm=1.0)
        pts_solid = generate(solid, cfg, stitch_mm=1.0)

        assert len(pts_donut) < len(pts_solid), (
            f"donut must have fewer stitches than solid ({len(pts_donut)} >= {len(pts_solid)})"
        )

        eps = 0.02   # guard against floating-point boundary artefacts
        cx, cy = outer / 2, outer / 2
        half   = inner / 2 - eps
        for x, y in pts_donut:
            inside = (cx - half < x < cx + half) and (cy - half < y < cy + half)
            assert not inside, f"stitch ({x:.3f},{y:.3f}) landed inside hole"

    def test_empty_polygon_returns_empty_list(self):
        from src.stitch.fill import generate

        cfg = FillConfig(spacing_mm=0.5, angle_deg=0.0, underlay=False)
        assert generate(Polygon(), cfg) == []

    def test_diagonal_fill_produces_points(self):
        """angle_deg=45 must still yield a non-empty point list."""
        from src.stitch.fill import generate

        cfg = FillConfig(spacing_mm=0.5, angle_deg=45.0, underlay=False)
        pts = generate(_square(10.0), cfg, stitch_mm=3.0)
        assert len(pts) > 0

    def test_all_points_inside_polygon(self):
        """Every generated stitch must lie within the source polygon."""
        from shapely.geometry import Point

        from src.stitch.fill import generate

        sq  = _square(10.0)
        cfg = FillConfig(spacing_mm=1.0, angle_deg=30.0, underlay=False)
        for x, y in generate(sq, cfg, stitch_mm=3.0):
            assert sq.buffer(0.05).contains(Point(x, y)), \
                f"({x:.3f},{y:.3f}) is outside the polygon"


class TestPullCompensation:
    def test_compensation_increases_row_count(self):
        """Pull compensation must produce >= as many stitches as no compensation."""
        from src.stitch.fill import generate

        sq   = _square(10.0)
        cfg  = FillConfig(spacing_mm=1.0, angle_deg=0.0, underlay=False)
        n0   = len(generate(sq, cfg, stitch_mm=3.0, pull_compensation_mm=0.0))
        n1   = len(generate(sq, cfg, stitch_mm=3.0, pull_compensation_mm=0.5))
        assert n1 >= n0

    def test_zero_compensation_is_identity(self):
        """pull_compensation_mm=0 must leave the polygon unchanged."""
        from src.stitch.fill import _apply_pull_compensation

        sq  = _square(10.0)
        out = _apply_pull_compensation(sq, 0.0, 0.0)
        assert abs(out.area - sq.area) < 1e-9


class TestFillBoustrophedon:
    def test_consecutive_points_no_huge_jump(self):
        """Within a filled square no two consecutive stitches should jump > stitch_mm + spacing."""
        from src.stitch.fill import generate

        sq = _square(10.0)
        stitch_mm  = 4.0
        spacing_mm = 1.0
        cfg  = FillConfig(spacing_mm=spacing_mm, angle_deg=0.0, underlay=False)
        pts  = generate(sq, cfg, stitch_mm=stitch_mm)

        # Max reasonable jump: within a row ≤ stitch_mm; row transition ≤ spacing_mm
        max_jump = stitch_mm + spacing_mm + 0.5   # small buffer for rounding
        for i in range(len(pts) - 1):
            d = math.hypot(pts[i+1][0] - pts[i][0], pts[i+1][1] - pts[i][1])
            assert d <= max_jump, f"jump {d:.2f} mm between pts {i} and {i+1}"


# ══════════════════════════════════════════════════════════════════════════════
# running.py
# ══════════════════════════════════════════════════════════════════════════════

class TestRunningGenerateLine:
    def test_point_count_for_known_line(self):
        """10 mm line at 2.5 mm spacing → 5 points (0, 2.5, 5, 7.5, 10)."""
        from src.stitch.running import generate_line

        pts = generate_line(LineString([(0, 0), (10, 0)]), spacing_mm=2.5)
        assert len(pts) == 5

    def test_empty_line_returns_empty(self):
        from src.stitch.running import generate_line

        assert generate_line(LineString(), 1.0) == []

    def test_endpoints_included(self):
        from src.stitch.running import generate_line

        pts = generate_line(LineString([(0, 0), (10, 0)]), spacing_mm=3.0)
        assert pytest.approx(pts[0][0],  abs=0.01) == 0.0
        assert pytest.approx(pts[-1][0], abs=0.01) == 10.0

    def test_generate_outline_uses_exterior(self):
        """generate_outline must return points on the polygon perimeter."""
        from shapely.geometry import Point

        from src.stitch.running import generate_outline

        sq  = _square(10.0)
        cfg = Config(min_stitch_mm=2.0)
        pts = generate_outline(sq, cfg)

        assert len(pts) > 0
        exterior = sq.exterior
        for x, y in pts:
            dist = exterior.distance(Point(x, y))
            assert dist < 0.02, f"({x:.3f},{y:.3f}) is not on the exterior"


# ══════════════════════════════════════════════════════════════════════════════
# satin.py
# ══════════════════════════════════════════════════════════════════════════════

class TestSatinGenerate:
    def test_returns_stitch_pairs(self):
        """Satin must return an even number of points (stitch pairs)."""
        from src.stitch.satin import generate

        rect = _rect(w=20.0, h=3.0)   # 3 mm wide — within satin range
        cfg  = SatinConfig(min_width_mm=1.0, max_width_mm=8.0, density_mm=0.4)
        pts  = generate(rect, cfg)

        assert len(pts) > 0
        assert len(pts) % 2 == 0, "satin must yield an even number of points"

    def test_too_wide_returns_empty(self):
        from src.stitch.satin import generate

        wide = _rect(w=20.0, h=10.0)  # 10 mm > max 8 mm
        cfg  = SatinConfig(min_width_mm=1.0, max_width_mm=8.0, density_mm=0.4)
        assert generate(wide, cfg) == []

    def test_too_narrow_returns_empty(self):
        from src.stitch.satin import generate

        thin = _rect(w=20.0, h=0.5)   # 0.5 mm < min 1 mm
        cfg  = SatinConfig(min_width_mm=1.0, max_width_mm=8.0, density_mm=0.4)
        assert generate(thin, cfg) == []

    def test_empty_polygon_returns_empty(self):
        from src.stitch.satin import generate

        cfg = SatinConfig(min_width_mm=1.0, max_width_mm=8.0, density_mm=0.4)
        assert generate(Polygon(), cfg) == []

    def test_stitch_pairs_span_full_width(self):
        """Each stitch pair must span close to the polygon width."""
        from src.stitch.satin import generate, width_at

        rect = _rect(w=20.0, h=4.0)
        cfg  = SatinConfig(min_width_mm=1.0, max_width_mm=8.0, density_mm=0.5)
        pts  = generate(rect, cfg)

        w = width_at(rect)
        # Successive pairs: distance between p[2i] and p[2i+1] ≈ width
        for i in range(0, len(pts) - 1, 2):
            dist = math.hypot(pts[i+1][0] - pts[i][0], pts[i+1][1] - pts[i][1])
            assert abs(dist - w) < w * 0.15, \
                f"pair span {dist:.2f} deviates >15% from width {w:.2f}"


class TestWidthAt:
    def test_axis_aligned_rect(self):
        from src.stitch.satin import width_at

        assert pytest.approx(width_at(_rect(20, 3)), abs=0.01) == 3.0

    def test_rotated_rect(self):
        """Width must be stable under rotation."""
        from src.stitch.satin import width_at

        rect    = _rect(20.0, 3.0)
        rotated = shp_rotate(rect, 45)
        assert pytest.approx(width_at(rotated), abs=0.1) == 3.0


# ══════════════════════════════════════════════════════════════════════════════
# underlay.py
# ══════════════════════════════════════════════════════════════════════════════

class TestUnderlayGenerate:
    def test_returns_points_for_valid_polygon(self):
        from src.stitch.underlay import generate

        cfg = FillConfig(spacing_mm=0.4, angle_deg=45.0, underlay=True)
        pts = generate(_square(10.0), cfg)
        assert len(pts) > 0

    def test_empty_polygon_returns_empty(self):
        from src.stitch.underlay import generate

        cfg = FillConfig(spacing_mm=0.4, angle_deg=45.0, underlay=True)
        assert generate(Polygon(), cfg) == []

    def test_underlay_then_fill_produces_more_points(self):
        """Fill with underlay=True must yield strictly more points than without."""
        from src.stitch.fill import generate

        sq         = _square(10.0)
        cfg_under  = FillConfig(spacing_mm=0.5, angle_deg=0.0, underlay=True)
        cfg_nounder = FillConfig(spacing_mm=0.5, angle_deg=0.0, underlay=False)

        n_under  = len(generate(sq, cfg_under,   stitch_mm=3.0))
        n_direct = len(generate(sq, cfg_nounder, stitch_mm=3.0))

        assert n_under > n_direct

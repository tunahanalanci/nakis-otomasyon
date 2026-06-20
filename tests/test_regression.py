"""Regression tests: arctura_logo.png must produce correct fill and scale."""

from __future__ import annotations

from pathlib import Path

import pyembroidery
import pytest

from src.config import Config, FillConfig, HoopConfig, SatinConfig, load
from src.pipeline import run

LOGO = Path(__file__).parent.parent / "samples" / "arctura_logo.png"
DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "default.json"
TARGET_W_MM = 80.0
TARGET_H_MM = 60.0
TOLERANCE   = 0.05   # ±5 % (logo has natural whitespace padding)
MIN_STITCHES = 3_000  # fill must produce at least this many stitches


def _logo_cfg() -> Config:
    cfg = load(DEFAULT_CONFIG)
    cfg.width_mm             = TARGET_W_MM
    cfg.height_mm            = TARGET_H_MM
    cfg.max_colors           = 1
    cfg.fill                 = FillConfig(spacing_mm=0.4, angle_deg=45, underlay=False)
    cfg.satin                = SatinConfig(min_width_mm=1.0, max_width_mm=8.0, density_mm=0.4)
    cfg.hoop                 = HoopConfig(w=200, h=200)
    cfg.pull_compensation_mm = 0.0
    return cfg


@pytest.fixture(scope="module")
def logo_result(tmp_path_factory):
    if not LOGO.exists():
        pytest.skip(f"Sample not found: {LOGO}")
    out = tmp_path_factory.mktemp("regression")
    cfg = _logo_cfg()
    return run(str(LOGO), cfg, str(out))


@pytest.fixture(scope="module")
def dst_pattern(logo_result):
    return pyembroidery.read(str(logo_result.dst_path))


# ── (a) Bounding box ~80 mm ±2% ───────────────────────────────────────────────

class TestScale:
    def test_dst_width_within_tolerance(self, dst_pattern):
        pts = [(s[0], s[1]) for s in dst_pattern.stitches if s[2] == pyembroidery.STITCH]
        assert pts, "DST has no STITCH commands"
        xs = [p[0] for p in pts]
        actual_w = (max(xs) - min(xs)) / 10.0
        assert actual_w == pytest.approx(TARGET_W_MM, rel=TOLERANCE), (
            f"Width {actual_w:.1f} mm is outside ±{TOLERANCE*100:.0f}% of {TARGET_W_MM} mm"
        )

    def test_dst_height_within_tolerance(self, dst_pattern):
        pts = [(s[0], s[1]) for s in dst_pattern.stitches if s[2] == pyembroidery.STITCH]
        ys  = [p[1] for p in pts]
        actual_h = (max(ys) - min(ys)) / 10.0
        assert actual_h == pytest.approx(TARGET_H_MM, rel=TOLERANCE), (
            f"Height {actual_h:.1f} mm is outside ±{TOLERANCE*100:.0f}% of {TARGET_H_MM} mm"
        )


# ── (b) Stitch count proves fill is working ───────────────────────────────────

class TestFill:
    def test_stitch_count_above_minimum(self, logo_result):
        assert logo_result.total_stitches >= MIN_STITCHES, (
            f"Only {logo_result.total_stitches} stitches — fill may not be working "
            f"(expected >= {MIN_STITCHES})"
        )

    def test_dst_readable(self, dst_pattern):
        assert dst_pattern is not None
        assert len(dst_pattern.stitches) > 0

    def test_has_stitch_commands(self, dst_pattern):
        n = sum(1 for s in dst_pattern.stitches if s[2] == pyembroidery.STITCH)
        assert n >= MIN_STITCHES


# ── (c) Colour block count ────────────────────────────────────────────────────

class TestColorBlocks:
    def test_color_block_count(self, logo_result):
        # Logo is 1 color: should produce exactly 1 color block
        assert logo_result.n_color_blocks == 1, (
            f"Expected 1 color block, got {logo_result.n_color_blocks}"
        )

    def test_color_report_created(self, logo_result):
        assert logo_result.color_report_path.exists()
        text = logo_result.color_report_path.read_text(encoding="utf-8")
        assert "RGB" in text


# ── (d) Holes: no stitches inside star/counter areas ─────────────────────────

class TestHoles:
    def test_validation_has_no_errors(self, logo_result):
        assert logo_result.validation.errors == [], (
            f"Validation errors: {logo_result.validation.errors}"
        )

    def test_no_stitches_at_star_center(self, dst_pattern, logo_result):
        """
        The ARCTURA logo has white stars roughly at the left and right edges
        of the design bounding box.  Sample the center of where the left star
        should be and verify there are no stitch points in that small region.

        Approximate star position: leftmost ~10% of width, vertically centered.
        We use a 2 mm² sample box in DST units.
        """
        pts = [(s[0], s[1]) for s in dst_pattern.stitches if s[2] == pyembroidery.STITCH]
        if not pts:
            pytest.skip("No stitch points")

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        width_dst    = max_x - min_x
        height_dst   = max_y - min_y

        # Left star: roughly 8-14% from left edge, 35-65% from top
        star_cx = min_x + int(width_dst  * 0.11)
        star_cy = min_y + int(height_dst * 0.50)
        radius  = int(0.8 * 10)  # 0.8 mm in DST units

        stitches_in_hole = sum(
            1 for x, y in pts
            if abs(x - star_cx) < radius and abs(y - star_cy) < radius
        )
        assert stitches_in_hole == 0, (
            f"{stitches_in_hole} stitches found inside expected star hole area"
        )


# ── Unit tests: coordinate conversions ───────────────────────────────────────

class TestConversions:
    def test_mm_to_dst(self):
        from src.export_dst import _to_dst
        assert _to_dst(1.0)  == 10
        assert _to_dst(0.1)  == 1
        assert _to_dst(10.0) == 100
        assert _to_dst(0.0)  == 0

    def test_px_per_mm_scale(self):
        """px_per_mm = image_width_px / width_mm."""
        image_px = 800
        width_mm = 80.0
        px_per_mm = image_px / width_mm
        assert px_per_mm == pytest.approx(10.0)

    def test_fill_skips_hole(self, tmp_path):
        """A donut polygon must produce fewer stitches than a solid polygon of same outer size."""
        from shapely.geometry import LinearRing, Polygon
        from src.config import FillConfig
        from src.stitch.fill import generate

        outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
        solid = Polygon(outer)
        hole  = Polygon(outer, [[(3, 3), (7, 3), (7, 7), (3, 7)]])

        cfg = FillConfig(spacing_mm=1.0, angle_deg=0.0, underlay=False)
        pts_solid = generate(solid, cfg, stitch_mm=1.0)
        pts_hole  = generate(hole,  cfg, stitch_mm=1.0)

        assert len(pts_solid) > 0
        assert len(pts_hole)  > 0
        assert len(pts_hole) < len(pts_solid), (
            f"Hole polygon ({len(pts_hole)}) must have fewer stitches than solid ({len(pts_solid)})"
        )

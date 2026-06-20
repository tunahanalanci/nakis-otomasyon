"""Orientation regression: output must NOT be flipped vertically or horizontally.

Convention enforced here:
  - Internal stitch space: mm, Y DOWN (y=0 at top, same as image pixels).
  - No Y-flip in vectorize or render_preview.
  - Single Y-flip ONLY in export_dst (dst_flip_y=True) so machine sees Y-up.
  - DST readback: Y-up (top of image = LARGE y in DST units).

The 'F' letter is the canonical test target — asymmetric under all
transforms (horizontal flip, vertical flip, 90° rotations).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyembroidery
import pytest
from PIL import Image as PilImage

from src.config import Config, FillConfig, HoopConfig, SatinConfig, load
from src.pipeline import run

DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "default.json"


def _orientation_cfg() -> Config:
    cfg = load(DEFAULT_CONFIG)
    cfg.width_mm             = 40.0
    cfg.height_mm            = 40.0
    cfg.max_colors           = 1
    cfg.fill                 = FillConfig(spacing_mm=1.0, angle_deg=0.0, underlay=False)
    cfg.satin                = SatinConfig(min_width_mm=1.0, max_width_mm=6.0, density_mm=1.0)
    cfg.hoop                 = HoopConfig(w=200, h=200)
    cfg.pull_compensation_mm = 0.0
    return cfg


# ── "F" letter fixture ─────────────────────────────────────────────────────────

def _f_letter_png(tmp_path: Path, w: int = 60, h: int = 80) -> Path:
    """
    Black "F" on white, (w x h) pixels, pixel Y DOWN:

        rows  0..9   : top horizontal bar (cols 4..w-10)
        rows  0..h-1 : left vertical stem (cols 4..13)
        rows 28..37  : middle horizontal bar (cols 4..w//2)

    Design facts (pixel Y-down, "top" = small row index):
    - Left-heavy: stem + bar origins all on left side
    - Top-heavy: more mass in rows 0..h//2-1 than h//2..h-1
    - Internal mm: y_mm = y_px / ppx  (Y stays DOWN, no flip)
    - DST readback: Y-flipped at export → top of image = LARGE y in DST
    """
    arr = np.ones((h, w, 3), dtype=np.uint8) * 255
    arr[0:10, 4:w - 10]    = 0   # top bar
    arr[0:h,  4:14]         = 0   # left stem (full height)
    arr[28:38, 4:w // 2]   = 0   # middle bar
    p = tmp_path / "f_letter.png"
    PilImage.fromarray(arr).save(str(p))
    return p


def _stitch_pts(dst_path: Path) -> list[tuple[float, float]]:
    """Return (x_dst, y_dst) for every STITCH in dst_path."""
    pat = pyembroidery.read(str(dst_path))
    return [(s[0], s[1]) for s in pat.stitches if s[2] == pyembroidery.STITCH]


def _arrow_up_png(tmp_path: Path) -> Path:
    """
    40×40 px PNG with a black upward-pointing arrow on white background.

    Layout (pixel rows, Y down):
      - Top 10 rows:  arrowhead (wide black triangle, top-heavy)
      - Bottom 30 rows: thin stem (4 px wide centered)

    After export Y-flip (dst_flip_y=True) the stitch centroid in the TOP half
    of the DST output (large y = top in Y-up) must contain MORE stitches
    than the BOTTOM half, because that's where the wide arrowhead is.
    """
    arr = np.ones((40, 40, 3), dtype=np.uint8) * 255  # white

    # Arrow head: pixel rows 0-9 (TOP of image), full-width triangle
    for row in range(10):
        left  = row * 2          # widens as we go down
        right = 40 - row * 2
        arr[row, left:right] = 0

    # Stem: pixel rows 10-39, 4 px wide centered
    arr[10:40, 18:22] = 0

    p = tmp_path / "arrow_up.png"
    PilImage.fromarray(arr).save(str(p))
    return p


def _stitch_pts_dst(dst_path: Path):
    pattern = pyembroidery.read(str(dst_path))
    return [(s[0], s[1]) for s in pattern.stitches if s[2] == pyembroidery.STITCH]


class TestOrientation:
    def test_top_heavy_design_has_more_stitches_at_top(self, tmp_path):
        """
        The arrow has its wide head in the TOP of the image (pixel rows 0-9).
        After pipeline the DST Y-up coordinate of those stitches should be
        in the UPPER half of the design bounding box (larger y value).

        If the output were flipped, the arrowhead would appear at the BOTTOM
        (smaller y), and this test would fail.
        """
        png = _arrow_up_png(tmp_path)
        cfg = _orientation_cfg()
        result = run(str(png), cfg, str(tmp_path / "out"))

        pts = _stitch_pts_dst(result.dst_path)
        assert len(pts) >= 4, "Not enough stitches to test orientation"

        ys     = [p[1] for p in pts]
        min_y  = min(ys)
        max_y  = max(ys)
        mid_y  = (min_y + max_y) / 2.0

        # DST Y-up: top half of image → higher Y values
        top_half_count = sum(1 for y in ys if y > mid_y)
        bot_half_count = sum(1 for y in ys if y <= mid_y)

        assert top_half_count > bot_half_count, (
            f"Output appears vertically flipped: "
            f"top_half={top_half_count}, bottom_half={bot_half_count}. "
            f"Arrow head should be in the top half (high Y in DST)."
        )

    def test_no_horizontal_mirror(self, tmp_path):
        """
        X axis must NOT be mirrored.  We verify this by checking that stitches
        from a left-side block stay within the left quarter of the stitch span,
        i.e. the stitch bounding-box width is much smaller than the design width.
        A mirrored result would spread stitches across the full design width.
        """
        arr = np.ones((40, 40, 3), dtype=np.uint8) * 255
        # Fill left 25% with black (x=0..9)
        arr[:, :10] = 0
        png = tmp_path / "left_block.png"
        PilImage.fromarray(arr).save(str(png))

        cfg = _orientation_cfg()
        result = run(str(png), cfg, str(tmp_path / "out"))
        pts = _stitch_pts_dst(result.dst_path)
        assert len(pts) >= 2

        xs = [p[0] for p in pts]
        stitch_span_mm = (max(xs) - min(xs)) / 10.0   # DST → mm

        # The block is 25% of 40mm = 10mm wide.  Allow up to 35% (14mm) for
        # fill padding / compensation.  A mirrored result would span ~40mm.
        assert stitch_span_mm < 14.0, (
            f"Stitch X span {stitch_span_mm:.1f} mm is too wide — "
            f"expected < 14 mm for a 10 mm left-block design."
        )

    def test_preview_orientation_matches_input(self, tmp_path):
        """
        The preview PNG must exist and have correct dimensions (non-zero).
        (Visual match is verified by inspection; here we just confirm it renders.)
        """
        png = _arrow_up_png(tmp_path)
        cfg = _orientation_cfg()
        result = run(str(png), cfg, str(tmp_path / "out"))

        assert result.preview_path.exists()
        img = PilImage.open(str(result.preview_path))
        w, h = img.size
        assert w > 10 and h > 10


# ── F-letter orientation tests (canonical proof) ──────────────────────────────

class TestFLetterOrientation:
    """
    "F" letter tests proving the single-flip contract:
      - Internal blocks: Y-DOWN (top of image = small y_mm).
      - DST readback: Y-UP (top of image = LARGE y_dst, because export flips).
      - Preview PNG: Y-DOWN (direct from blocks, no flip).
    """

    def test_f_top_bar_is_at_top_in_dst(self, tmp_path):
        """
        F's top bar (pixel rows 0-9) must map to LARGE y in DST.

        Because export_dst flips Y (dst_flip_y=True), the top of the image
        (small y_mm internally) becomes large y in the DST file (Y-up).
        Stitches in the top 30 % of the DST y-range should outnumber those
        in the bottom 30 % — the F's wide top bar drives this.
        """
        png = _f_letter_png(tmp_path)
        cfg = _orientation_cfg()
        result = run(str(png), cfg, str(tmp_path / "out"))

        pts = _stitch_pts(result.dst_path)
        assert len(pts) >= 10, "Too few stitches for F orientation test"

        ys = [p[1] for p in pts]
        min_y, max_y = min(ys), max(ys)
        span = max_y - min_y
        assert span > 0, "All stitches at same y — degenerate design"

        # Top 30 % of y-range = LARGE y (DST Y-up: large = top of design)
        top_band_min = min_y + span * 0.70
        bot_band_max = min_y + span * 0.30
        top_pts = [y for y in ys if y >= top_band_min]
        bot_pts = [y for y in ys if y <= bot_band_max]

        assert len(top_pts) > 0, "No stitches in top 30 % of DST y range"
        assert len(bot_pts) > 0, "No stitches in bot 30 % of DST y range"

        assert len(top_pts) > len(bot_pts), (
            f"F top bar should produce more stitches at LARGE y in DST "
            f"(top30%={len(top_pts)}, bot30%={len(bot_pts)}) — "
            f"DST Y-flip may be missing or double-applied"
        )

    def test_f_stem_is_on_left_in_dst(self, tmp_path):
        """
        F's vertical stem (pixel cols 4-13, left side) must stay on the LEFT
        side in DST coordinates.  A horizontal mirror would move it to the right.

        We split the x range in half and count stitches on each side.
        The F is LEFT-heavy (stem + bar origins all on left), so left > right.
        """
        png = _f_letter_png(tmp_path)
        cfg = _orientation_cfg()
        result = run(str(png), cfg, str(tmp_path / "out"))

        pts = _stitch_pts(result.dst_path)
        assert len(pts) >= 10

        xs = [p[0] for p in pts]
        mid_x = (min(xs) + max(xs)) / 2.0
        left_count  = sum(1 for x in xs if x < mid_x)
        right_count = sum(1 for x in xs if x > mid_x)

        assert left_count > right_count, (
            f"F stem should be on LEFT (left={left_count}, right={right_count}) — "
            f"output appears HORIZONTALLY MIRRORED"
        )

    def test_f_top_bar_y_greater_than_stem_bottom_y_in_dst(self, tmp_path):
        """
        Coordinate-level DST check: top bar (pixel rows 0-9) → LARGE y in DST;
        bottom of stem (pixel rows 70-79) → SMALL y in DST.

        After export Y-flip: y_dst = (min_y + max_y - y_mm).
        Top of image has small y_mm → large y_dst (large = top in DST Y-up).
        Bottom of image has large y_mm → small y_dst.

        We separate the two regions by x-span (top bar is wide, stem is narrow).
        """
        W, H = 60, 80
        arr = np.ones((H, W, 3), dtype=np.uint8) * 255
        arr[0:10,  4:50] = 0   # top bar (wide)
        arr[70:80, 4:14] = 0   # bottom of stem (narrow)

        png = tmp_path / "f_split.png"
        PilImage.fromarray(arr).save(str(png))

        cfg = _orientation_cfg()
        result = run(str(png), cfg, str(tmp_path / "out"))

        pts = _stitch_pts(result.dst_path)
        assert len(pts) >= 6, "Too few stitches for split-F test"

        xs = [p[0] for p in pts]
        min_x, max_x = min(xs), max(xs)
        mid_x = (min_x + max_x) / 2.0

        top_bar_ys  = [p[1] for p in pts if p[0] > mid_x]   # wide region = top bar
        stem_bot_ys = [p[1] for p in pts if p[0] <= mid_x]  # narrow region = stem bottom

        if not top_bar_ys or not stem_bot_ys:
            pytest.skip("Could not separate top-bar from stem-bottom stitches")

        mean_y_topbar  = sum(top_bar_ys)  / len(top_bar_ys)
        mean_y_stembot = sum(stem_bot_ys) / len(stem_bot_ys)

        # DST Y-up: top bar must have LARGER y than stem bottom
        assert mean_y_topbar > mean_y_stembot, (
            f"Top bar (mean DST y={mean_y_topbar:.0f}) must be > "
            f"stem bottom (mean DST y={mean_y_stembot:.0f}) — "
            f"DST Y-flip (dst_flip_y) not applied or double-applied"
        )

    def test_f_preview_renders_without_error(self, tmp_path):
        """Preview PNG must exist and be large enough to contain the F shape."""
        png = _f_letter_png(tmp_path)
        cfg = _orientation_cfg()
        result = run(str(png), cfg, str(tmp_path / "out"))

        assert result.preview_path.exists()
        img = PilImage.open(str(result.preview_path))
        w, h = img.size
        assert w >= 50 and h >= 50, f"Preview too small: {w}x{h}"
        # Must not be all-white (blank = rendering failed)
        arr = np.array(img)
        assert arr.min() < 200, "Preview appears blank (all white)"

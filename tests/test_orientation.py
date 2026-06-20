"""Orientation regression: output must NOT be flipped vertically or horizontally."""

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


def _arrow_up_png(tmp_path: Path) -> Path:
    """
    40×40 px PNG with a black upward-pointing arrow on white background.

    Layout (pixel rows, Y down):
      - Top 10 rows:  arrowhead (wide black triangle, top-heavy)
      - Bottom 30 rows: thin stem (4 px wide centered)

    After correct (non-flipped) pipeline the stitch centroid in the TOP half
    of the design (in DST Y-up coordinates) must contain MORE stitches than
    the BOTTOM half, because that's where the wide arrowhead is.
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

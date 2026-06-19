"""End-to-end pipeline test: PNG → DST round-trip validation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyembroidery
import pytest
from PIL import Image as PilImage

from src.config import Config, FillConfig, HoopConfig, SatinConfig, load
from src.pipeline import PipelineResult, run


DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "default.json"


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _fast_cfg(max_colors: int = 2) -> Config:
    """Config tuned for fast e2e tests: coarse fill, no underlay."""
    cfg = load(DEFAULT_CONFIG)
    cfg.max_colors       = max_colors
    cfg.width_mm         = 30.0
    cfg.height_mm        = 20.0
    cfg.fill             = FillConfig(spacing_mm=2.0, angle_deg=45.0, underlay=False)
    cfg.satin            = SatinConfig(min_width_mm=1.0, max_width_mm=6.0, density_mm=1.0)
    cfg.pull_compensation_mm = 0.0
    cfg.hoop             = HoopConfig(w=200, h=200)
    return cfg


def _two_color_png(tmp_path: Path) -> Path:
    """Create a simple 2-colour synthetic PNG."""
    arr = np.zeros((40, 60, 3), dtype=np.uint8)
    arr[:20, :] = [200, 40,  40]   # red half
    arr[20:, :] = [40,  80, 200]   # blue half
    p = tmp_path / "two_color.png"
    PilImage.fromarray(arr).save(str(p))
    return p


def _three_color_png(tmp_path: Path) -> Path:
    """Create a simple 3-colour synthetic PNG (horizontal stripes)."""
    arr = np.zeros((60, 90, 3), dtype=np.uint8)
    arr[:20, :]  = [200, 40,  40]
    arr[20:40,:] = [40,  160, 60]
    arr[40:, :]  = [40,  80, 200]
    p = tmp_path / "three_color.png"
    PilImage.fromarray(arr).save(str(p))
    return p


# ── Core round-trip test ──────────────────────────────────────────────────────

class TestPipelineRoundTrip:
    def test_dst_file_is_created(self, tmp_path):
        png  = _two_color_png(tmp_path)
        cfg  = _fast_cfg(max_colors=2)
        result = run(str(png), cfg, str(tmp_path / "out"))
        assert result.dst_path.exists(), "DST file not created"
        assert result.dst_path.suffix == ".dst"

    def test_dst_is_readable_by_pyembroidery(self, tmp_path):
        """pyembroidery must parse the output DST without raising."""
        png  = _two_color_png(tmp_path)
        cfg  = _fast_cfg(max_colors=2)
        result = run(str(png), cfg, str(tmp_path / "out"))
        pattern = pyembroidery.read(str(result.dst_path))
        assert pattern is not None
        assert len(pattern.stitches) > 0

    def test_dst_contains_stitch_commands(self, tmp_path):
        """The read-back DST must have at least a few STITCH commands."""
        png    = _two_color_png(tmp_path)
        cfg    = _fast_cfg(max_colors=2)
        result = run(str(png), cfg, str(tmp_path / "out"))
        pattern = pyembroidery.read(str(result.dst_path))
        n_stitches = sum(1 for s in pattern.stitches if s[2] == pyembroidery.STITCH)
        assert n_stitches > 0, "DST has no STITCH commands"

    def test_preview_png_created(self, tmp_path):
        png  = _two_color_png(tmp_path)
        cfg  = _fast_cfg(max_colors=2)
        result = run(str(png), cfg, str(tmp_path / "out"))
        assert result.preview_path.exists()
        img = PilImage.open(str(result.preview_path))
        assert img.mode == "RGB"
        assert img.size[0] > 1 and img.size[1] > 1

    def test_color_report_created(self, tmp_path):
        png  = _two_color_png(tmp_path)
        cfg  = _fast_cfg(max_colors=2)
        result = run(str(png), cfg, str(tmp_path / "out"))
        assert result.color_report_path.exists()
        text = result.color_report_path.read_text(encoding="utf-8")
        assert "RGB" in text
        assert "1 ->" in text

    def test_pipeline_result_type(self, tmp_path):
        png  = _two_color_png(tmp_path)
        cfg  = _fast_cfg(max_colors=2)
        result = run(str(png), cfg, str(tmp_path / "out"))
        assert isinstance(result, PipelineResult)

    def test_validation_ok_for_small_design(self, tmp_path):
        """A 30×20 mm design must pass hoop validation for a 200×200 mm hoop."""
        png  = _two_color_png(tmp_path)
        cfg  = _fast_cfg(max_colors=2)
        result = run(str(png), cfg, str(tmp_path / "out"))
        assert result.validation.errors == [], (
            f"Unexpected errors: {result.validation.errors}"
        )

    def test_stitch_count_is_positive(self, tmp_path):
        png  = _two_color_png(tmp_path)
        cfg  = _fast_cfg(max_colors=2)
        result = run(str(png), cfg, str(tmp_path / "out"))
        assert result.total_stitches > 0

    def test_bounds_are_within_hoop(self, tmp_path):
        png  = _two_color_png(tmp_path)
        cfg  = _fast_cfg(max_colors=2)
        result = run(str(png), cfg, str(tmp_path / "out"))
        minx, miny, maxx, maxy = result.bounds_mm
        assert maxx - minx <= cfg.hoop.w
        assert maxy - miny <= cfg.hoop.h


# ── Three-colour design ───────────────────────────────────────────────────────

class TestThreeColor:
    def test_three_color_dst_readable(self, tmp_path):
        png  = _three_color_png(tmp_path)
        cfg  = _fast_cfg(max_colors=3)
        result = run(str(png), cfg, str(tmp_path / "out"))
        pattern = pyembroidery.read(str(result.dst_path))
        n_stitches = sum(1 for s in pattern.stitches if s[2] == pyembroidery.STITCH)
        assert n_stitches > 0

    def test_three_color_report_lists_colours(self, tmp_path):
        png  = _three_color_png(tmp_path)
        cfg  = _fast_cfg(max_colors=3)
        result = run(str(png), cfg, str(tmp_path / "out"))
        text = result.color_report_path.read_text(encoding="utf-8")
        assert "1 ->" in text


# ── Debug mode ────────────────────────────────────────────────────────────────

class TestDebugMode:
    def test_debug_creates_color_debug_png(self, tmp_path):
        png  = _two_color_png(tmp_path)
        cfg  = _fast_cfg(max_colors=2)
        run(str(png), cfg, str(tmp_path / "out"), debug=True)
        debug_png = tmp_path / "out" / "two_color_debug_colors.png"
        assert debug_png.exists(), "Debug colour PNG not created"

    def test_no_debug_does_not_create_debug_png(self, tmp_path):
        png  = _two_color_png(tmp_path)
        cfg  = _fast_cfg(max_colors=2)
        run(str(png), cfg, str(tmp_path / "out"), debug=False)
        debug_png = tmp_path / "out" / "two_color_debug_colors.png"
        assert not debug_png.exists()


# ── Sample files ──────────────────────────────────────────────────────────────

class TestSampleFiles:
    """Verify that the bundled sample PNGs run through the pipeline."""

    SAMPLES_DIR = Path(__file__).parent.parent / "samples"

    @pytest.mark.parametrize("fname", ["iki_renk.png", "uc_renk.png"])
    def test_sample_produces_dst(self, tmp_path, fname):
        sample = self.SAMPLES_DIR / fname
        if not sample.exists():
            pytest.skip(f"Sample not found: {sample}")
        max_c = 2 if "iki" in fname else 3
        cfg   = _fast_cfg(max_colors=max_c)
        result = run(str(sample), cfg, str(tmp_path / "out"))
        assert result.dst_path.exists()
        assert result.total_stitches > 0

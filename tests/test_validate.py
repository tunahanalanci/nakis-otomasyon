"""Tests for src/validate.py."""

from __future__ import annotations

import pyembroidery
import pytest
from PIL import Image

from src.config import Config, HoopConfig
from src.validate import (
    ValidationReport,
    _length_violations,
    _stitch_points,
    render_preview,
    validate,
)


# ── DST fixture helpers ───────────────────────────────────────────────────────

def _write_simple_dst(tmp_path, stitches_xy: list[tuple[int, int]], suffix="test") -> "Path":
    """Write a minimal DST with the given (x, y) STITCH coordinates."""
    from pathlib import Path

    p = pyembroidery.EmbPattern()
    for x, y in stitches_xy:
        p.add_stitch_absolute(pyembroidery.STITCH, x, y)
    p.add_stitch_absolute(pyembroidery.END, 0, 0)
    dst = tmp_path / f"{suffix}.dst"
    pyembroidery.write(p, str(dst))
    return dst


# ── _stitch_points ────────────────────────────────────────────────────────────

class TestStitchPoints:
    def test_extracts_stitch_coords(self):
        raw = [[0, 0, pyembroidery.STITCH], [100, 0, pyembroidery.STITCH]]
        pts = _stitch_points(raw)
        assert len(pts) == 2
        assert (0, 0) in pts
        assert (100, 0) in pts

    def test_excludes_non_stitch_commands(self):
        raw = [
            [0,   0,  pyembroidery.JUMP],
            [100, 0,  pyembroidery.STITCH],
            [100, 0,  pyembroidery.END],
        ]
        pts = _stitch_points(raw)
        assert len(pts) == 1
        assert pts[0] == (100, 0)

    def test_empty_returns_empty(self):
        assert _stitch_points([]) == []


# ── _length_violations ────────────────────────────────────────────────────────

class TestLengthViolations:
    def test_no_violations_for_normal_stitches(self):
        # 10 mm (100 DST) apart — within [0.5, 12] mm
        raw = [
            [0,   0, pyembroidery.STITCH],
            [100, 0, pyembroidery.STITCH],
            [200, 0, pyembroidery.STITCH],
        ]
        short, long_ = _length_violations(raw, min_stitch_mm=0.5)
        assert short == 0
        assert long_ == 0

    def test_short_stitch_detected(self):
        # 2 DST = 0.2 mm < min_stitch_mm=0.5 mm
        raw = [
            [0, 0, pyembroidery.STITCH],
            [2, 0, pyembroidery.STITCH],
            [4, 0, pyembroidery.STITCH],
        ]
        short, long_ = _length_violations(raw, min_stitch_mm=0.5)
        assert short == 2
        assert long_ == 0

    def test_long_stitch_detected(self):
        # 130 DST = 13 mm > max 12 mm
        raw = [
            [0,   0, pyembroidery.STITCH],
            [130, 0, pyembroidery.STITCH],
        ]
        short, long_ = _length_violations(raw, min_stitch_mm=0.5)
        assert long_ == 1
        assert short == 0

    def test_non_stitch_resets_cursor(self):
        # Jump between two widely-spaced stitches must NOT flag a long stitch
        raw = [
            [0,   0, pyembroidery.STITCH],
            [0,   0, pyembroidery.JUMP],   # cursor reset
            [500, 0, pyembroidery.STITCH], # first after jump — no comparison
        ]
        short, long_ = _length_violations(raw, min_stitch_mm=0.5)
        assert short == 0
        assert long_ == 0


# ── validate ──────────────────────────────────────────────────────────────────

class TestValidate:
    def _cfg(self, hoop_w=200, hoop_h=200, min_stitch_mm=0.5):
        cfg = Config()
        cfg.hoop = HoopConfig(w=hoop_w, h=hoop_h)
        cfg.min_stitch_mm = min_stitch_mm
        return cfg

    def test_valid_design_returns_ok(self, tmp_path):
        # 10×10 mm design, well within 200×200 mm hoop
        dst = _write_simple_dst(tmp_path, [(0, 0), (100, 0), (100, 100), (0, 100)])
        report = validate(dst, self._cfg())
        assert isinstance(report, ValidationReport)
        assert report.ok is True
        assert report.errors == []

    def test_missing_file_returns_error(self, tmp_path):
        report = validate(tmp_path / "missing.dst", self._cfg())
        assert report.ok is False
        assert len(report.errors) == 1

    def test_hoop_width_overflow_flagged(self, tmp_path):
        # Design: 0 to 2500 DST = 250 mm, hoop only 200 mm wide
        dst = _write_simple_dst(tmp_path, [(0, 0), (2500, 0), (2500, 100)])
        report = validate(dst, self._cfg(hoop_w=200))
        assert report.ok is False
        assert any("genislik" in e or "kasnak" in e for e in report.errors)

    def test_hoop_height_overflow_flagged(self, tmp_path):
        dst = _write_simple_dst(tmp_path, [(0, 0), (0, 2500), (100, 2500)])
        report = validate(dst, self._cfg(hoop_h=200))
        assert report.ok is False
        assert any("yukseklik" in e or "kasnak" in e for e in report.errors)

    def test_short_stitches_produce_warning(self, tmp_path):
        # 2 DST = 0.2 mm << min_stitch_mm = 0.5 mm
        pts = [(i * 2, 0) for i in range(10)]
        dst = _write_simple_dst(tmp_path, pts)
        report = validate(dst, self._cfg(min_stitch_mm=0.5))
        # pyembroidery may add tie stitches; at least check the function runs
        assert isinstance(report, ValidationReport)
        # The short-stitch warning should fire for our synthetic short stitches
        assert any("kisa" in w for w in report.warnings)

    def test_density_warning_for_clustered_stitches(self, tmp_path):
        # 5×5 grid with 2-DST step → all coords in [0,8], all in the same
        # 10×10 DST (1mm²) density cell → 25 stitches in one cell > threshold 15
        pts = [(x * 2, y * 2) for y in range(5) for x in range(5)]
        dst = _write_simple_dst(tmp_path, pts)
        report = validate(dst, self._cfg(min_stitch_mm=0.0))
        assert isinstance(report, ValidationReport)
        assert any("yogunluk" in w for w in report.warnings)


# ── render_preview ────────────────────────────────────────────────────────────

class TestRenderPreview:
    def test_creates_png_file(self, tmp_path):
        dst = _write_simple_dst(tmp_path, [(0, 0), (300, 0), (300, 300), (0, 300)])
        out = tmp_path / "preview.png"
        result = render_preview(dst, out)
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 0

    def test_output_is_valid_image(self, tmp_path):
        dst = _write_simple_dst(tmp_path, [(0, 0), (400, 0), (400, 400), (0, 400)])
        out = tmp_path / "preview.png"
        render_preview(dst, out)
        img = Image.open(str(out))
        assert img.mode == "RGB"
        assert img.size[0] > 1 and img.size[1] > 1

    def test_empty_pattern_produces_fallback_image(self, tmp_path):
        # A pattern with only END and no stitches → 100×100 white image
        p = pyembroidery.EmbPattern()
        p.add_stitch_absolute(pyembroidery.END, 0, 0)
        dst = tmp_path / "empty.dst"
        pyembroidery.write(p, str(dst))
        out = tmp_path / "preview.png"
        render_preview(dst, out)
        assert out.exists()
        img = Image.open(str(out))
        assert img.size == (100, 100)

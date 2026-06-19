"""Tests for src/export_dst.py."""

from __future__ import annotations

import pytest

from src.config import Config
from src.export_dst import ExportStats, _group_by_color, _to_dst, _write_color_report, export
from src.optimize import StitchBlock


# ── _to_dst ───────────────────────────────────────────────────────────────────

class TestToDst:
    def test_one_mm(self):
        assert _to_dst(1.0) == 10

    def test_zero(self):
        assert _to_dst(0.0) == 0

    def test_ten_mm(self):
        assert _to_dst(10.0) == 100

    def test_point_one_mm(self):
        assert _to_dst(0.1) == 1   # 0.1 * 10 = 1.0 → 1

    def test_negative(self):
        assert _to_dst(-5.0) == -50


# ── _group_by_color ───────────────────────────────────────────────────────────

class TestGroupByColor:
    def test_single_colour(self):
        blocks = [StitchBlock(0, []), StitchBlock(0, [])]
        assert len(_group_by_color(blocks)) == 1

    def test_two_different_colours(self):
        blocks = [StitchBlock(0, []), StitchBlock(1, [])]
        segs = _group_by_color(blocks)
        assert len(segs) == 2

    def test_interleaved_creates_three_segments(self):
        blocks = [StitchBlock(0, []), StitchBlock(1, []), StitchBlock(0, [])]
        assert len(_group_by_color(blocks)) == 3

    def test_empty_input(self):
        assert _group_by_color([]) == []


# ── _write_color_report ───────────────────────────────────────────────────────

class TestWriteColorReport:
    def test_contains_rgb_values(self, tmp_path):
        segments = [[StitchBlock(0, [(0.0, 0.0), (1.0, 0.0)])]]
        palette  = [(255, 0, 0)]
        _write_color_report(segments, palette, tmp_path / "report.txt")
        text = (tmp_path / "report.txt").read_text(encoding="utf-8")
        assert "RGB(255,0,0)" in text

    def test_one_line_per_segment(self, tmp_path):
        segments = [
            [StitchBlock(0, [(0.0, 0.0), (1.0, 0.0)])],
            [StitchBlock(1, [(2.0, 0.0), (3.0, 0.0)])],
        ]
        palette = [(255, 0, 0), (0, 255, 0)]
        _write_color_report(segments, palette, tmp_path / "report.txt")
        text = (tmp_path / "report.txt").read_text(encoding="utf-8")
        assert "1 ->" in text
        assert "2 ->" in text

    def test_unknown_colour_index(self, tmp_path):
        segments = [[StitchBlock(99, [(0.0, 0.0), (1.0, 0.0)])]]
        _write_color_report(segments, [], tmp_path / "report.txt")
        text = (tmp_path / "report.txt").read_text(encoding="utf-8")
        assert "bilinmeyen" in text


# ── export ────────────────────────────────────────────────────────────────────

def _two_colour_blocks() -> list[StitchBlock]:
    return [
        StitchBlock(0, [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)]),
        StitchBlock(1, [(0.0, 5.0), (5.0, 5.0), (10.0, 5.0)]),
    ]


def _palette() -> list[tuple[int, int, int]]:
    return [(255, 0, 0), (0, 255, 0)]


class TestExport:
    def test_creates_dst_file(self, tmp_path):
        stats = export(_two_colour_blocks(), _palette(), Config(), tmp_path)
        assert stats.dst_path.exists()
        assert stats.dst_path.suffix == ".dst"

    def test_custom_stem(self, tmp_path):
        stats = export(_two_colour_blocks(), _palette(), Config(), tmp_path, stem="test_nakis")
        assert stats.dst_path.name == "test_nakis.dst"

    def test_stitch_count_matches_input_points(self, tmp_path):
        stats = export(_two_colour_blocks(), _palette(), Config(), tmp_path)
        assert stats.total_stitches == 6   # 3 pts × 2 blocks

    def test_n_color_blocks(self, tmp_path):
        stats = export(_two_colour_blocks(), _palette(), Config(), tmp_path)
        assert stats.n_color_blocks == 2

    def test_bounds_mm(self, tmp_path):
        stats = export(_two_colour_blocks(), _palette(), Config(), tmp_path)
        minx, miny, maxx, maxy = stats.bounds_mm
        assert pytest.approx(minx, abs=0.01) == 0.0
        assert pytest.approx(miny, abs=0.01) == 0.0
        assert pytest.approx(maxx, abs=0.01) == 10.0
        assert pytest.approx(maxy, abs=0.01) == 5.0

    def test_creates_renk_sirasi_txt(self, tmp_path):
        export(_two_colour_blocks(), _palette(), Config(), tmp_path)
        report = tmp_path / "renk_sirasi.txt"
        assert report.exists()
        text = report.read_text(encoding="utf-8")
        assert "RGB(255,0,0)" in text
        assert "RGB(0,255,0)" in text

    def test_returns_export_stats_type(self, tmp_path):
        stats = export(_two_colour_blocks(), _palette(), Config(), tmp_path)
        assert isinstance(stats, ExportStats)

    def test_empty_blocks(self, tmp_path):
        stats = export([], [], Config(), tmp_path)
        assert stats.total_stitches == 0
        assert stats.n_color_blocks == 0
        assert stats.dst_path.exists()

    def test_single_colour_no_color_change_needed(self, tmp_path):
        blocks = [
            StitchBlock(0, [(0.0, 0.0), (1.0, 0.0)]),
            StitchBlock(0, [(2.0, 0.0), (3.0, 0.0)]),
        ]
        stats = export(blocks, [(255, 0, 0)], Config(), tmp_path)
        assert stats.n_color_blocks == 1  # both same colour → 1 segment

    def test_out_dir_created_if_missing(self, tmp_path):
        new_dir = tmp_path / "subdir" / "nested"
        assert not new_dir.exists()
        export(_two_colour_blocks(), _palette(), Config(), new_dir)
        assert new_dir.exists()

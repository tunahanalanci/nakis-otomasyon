"""Tests for src/optimize.py."""

from __future__ import annotations

import pytest

from src.config import Config
from src.optimize import StitchBlock, _dist, _filter_short_stitches, _nearest_neighbor_sort, optimize


# ── StitchBlock ───────────────────────────────────────────────────────────────

class TestStitchBlock:
    def test_start_and_end(self):
        blk = StitchBlock(0, [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)])
        assert blk.start == (1.0, 2.0)
        assert blk.end   == (5.0, 6.0)

    def test_empty_block_returns_origin(self):
        blk = StitchBlock(0, [])
        assert blk.start == (0.0, 0.0)
        assert blk.end   == (0.0, 0.0)


# ── _filter_short_stitches ────────────────────────────────────────────────────

class TestFilterShortStitches:
    def test_removes_too_close_intermediate_point(self):
        pts = [(0.0, 0.0), (0.1, 0.0), (1.0, 0.0)]
        result = _filter_short_stitches(pts, min_mm=0.5)
        assert (0.1, 0.0) not in result
        assert result[0]  == (0.0, 0.0)
        assert result[-1] == (1.0, 0.0)

    def test_keeps_points_far_enough(self):
        pts = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        assert _filter_short_stitches(pts, min_mm=0.5) == pts

    def test_always_keeps_first_and_last(self):
        pts = [(0.0, 0.0), (0.01, 0.0), (0.02, 0.0)]
        result = _filter_short_stitches(pts, min_mm=1.0)
        assert result[0]  == (0.0, 0.0)
        assert result[-1] == (0.02, 0.0)

    def test_zero_min_returns_all(self):
        pts = [(0.0, 0.0), (0.001, 0.0), (1.0, 0.0)]
        assert _filter_short_stitches(pts, min_mm=0.0) == pts

    def test_single_point_returned_unchanged(self):
        pts = [(3.0, 4.0)]
        assert _filter_short_stitches(pts, min_mm=1.0) == pts


# ── _nearest_neighbor_sort ────────────────────────────────────────────────────

class TestNearestNeighborSort:
    def test_picks_closest_block_first(self):
        near = StitchBlock(0, [(1.0, 0.0), (2.0, 0.0)])
        far  = StitchBlock(0, [(10.0, 0.0), (11.0, 0.0)])
        result = _nearest_neighbor_sort([far, near], start=(0.0, 0.0))
        assert result[0].start == (1.0, 0.0)
        assert result[1].start == (10.0, 0.0)

    def test_reverses_block_when_end_is_closer(self):
        # End (0,0) is closer to cursor (0,0) than start (10,0)
        blk = StitchBlock(0, [(10.0, 0.0), (5.0, 0.0), (0.0, 0.0)])
        result = _nearest_neighbor_sort([blk], start=(0.0, 0.0))
        assert result[0].start == (0.0, 0.0)
        assert result[0].end   == (10.0, 0.0)

    def test_single_block_returned_as_is(self):
        blk = StitchBlock(0, [(0.0, 0.0), (1.0, 0.0)])
        result = _nearest_neighbor_sort([blk], start=(0.0, 0.0))
        assert len(result) == 1
        assert result[0].points == blk.points

    def test_empty_list_returns_empty(self):
        assert _nearest_neighbor_sort([], start=(0.0, 0.0)) == []


# ── optimize ──────────────────────────────────────────────────────────────────

def _cfg(**kwargs) -> Config:
    return Config(**kwargs)


class TestOptimize:
    def test_empty_input_returns_empty(self):
        assert optimize([], _cfg()) == []

    def test_single_block_preserved(self):
        pts = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        blk = StitchBlock(0, pts)
        result = optimize([blk], _cfg(min_stitch_mm=0.1))
        assert result[0].points == pts

    def test_drops_empty_blocks(self):
        blocks = [
            StitchBlock(0, []),
            StitchBlock(0, [(0.0, 0.0), (1.0, 0.0)]),
        ]
        result = optimize(blocks, _cfg())
        assert all(len(b.points) >= 2 for b in result)

    def test_drops_single_point_blocks(self):
        blocks = [
            StitchBlock(0, [(0.0, 0.0)]),
            StitchBlock(0, [(0.0, 0.0), (1.0, 0.0)]),
        ]
        result = optimize(blocks, _cfg())
        assert len(result) == 1

    def test_groups_same_colour_contiguously(self):
        """After optimisation no colour must reappear after a different colour."""
        blocks = [
            StitchBlock(0, [(0.0, 0.0), (1.0, 0.0)]),
            StitchBlock(1, [(5.0, 0.0), (6.0, 0.0)]),
            StitchBlock(0, [(2.0, 0.0), (3.0, 0.0)]),  # same colour as first
        ]
        result = optimize(blocks, _cfg())
        indices_by_color: dict[int, list[int]] = {}
        for i, blk in enumerate(result):
            indices_by_color.setdefault(blk.color_idx, []).append(i)
        for cidx, idxs in indices_by_color.items():
            assert idxs == list(range(idxs[0], idxs[-1] + 1)), (
                f"colour {cidx} blocks are not contiguous: {idxs}"
            )

    def test_filters_short_stitches(self):
        pts = [(0.0, 0.0), (0.01, 0.0), (2.0, 0.0)]
        result = optimize([StitchBlock(0, pts)], _cfg(min_stitch_mm=0.5))
        assert (0.01, 0.0) not in result[0].points

    def test_colour_order_preserves_first_seen(self):
        """First colour encountered must be sewn first."""
        blocks = [
            StitchBlock(1, [(0.0, 0.0), (1.0, 0.0)]),
            StitchBlock(0, [(2.0, 0.0), (3.0, 0.0)]),
        ]
        result = optimize(blocks, _cfg())
        assert result[0].color_idx == 1
        assert result[-1].color_idx == 0

    def test_all_blocks_present_in_output(self):
        blocks = [
            StitchBlock(0, [(0.0, 0.0), (1.0, 0.0)]),
            StitchBlock(1, [(5.0, 0.0), (6.0, 0.0)]),
            StitchBlock(0, [(2.0, 0.0), (3.0, 0.0)]),
        ]
        result = optimize(blocks, _cfg())
        assert sum(1 for b in result if b.color_idx == 0) == 2
        assert sum(1 for b in result if b.color_idx == 1) == 1

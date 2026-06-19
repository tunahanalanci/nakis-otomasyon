"""Tests for src.separate and src.vectorize."""

from __future__ import annotations

import math

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Polygon


# ── Helpers ────────────────────────────────────────────────────────────────────

def _circle(h: int, w: int, cy: float, cx: float, r: float) -> np.ndarray:
    """Boolean mask with a filled circle."""
    y, x = np.ogrid[:h, :w]
    return ((x - cx) ** 2 + (y - cy) ** 2) <= r ** 2


def _ring(h: int, w: int, cy: float, cx: float, r_out: float, r_in: float) -> np.ndarray:
    """Boolean mask: filled circle with a circular hole (ring / donut)."""
    y, x = np.ogrid[:h, :w]
    dist2 = (x - cx) ** 2 + (y - cy) ** 2
    return (dist2 <= r_out ** 2) & (dist2 > r_in ** 2)


# ══════════════════════════════════════════════════════════════════════════════
# src.separate
# ══════════════════════════════════════════════════════════════════════════════

class TestMasksFromLabels:
    def test_background_excluded_from_all_masks(self):
        from src.separate import masks_from_labels

        label_map = np.array([[-1, 0, 1], [0, -1, 1]], dtype=np.int32)
        masks = masks_from_labels(label_map, 2)

        assert not masks[0][0, 0], "background (-1) must be False in colour-0 mask"
        assert not masks[1][0, 0], "background (-1) must be False in colour-1 mask"

    def test_correct_pixels_set(self):
        from src.separate import masks_from_labels

        label_map = np.array([[-1, 0, 1], [0, -1, 1]], dtype=np.int32)
        masks = masks_from_labels(label_map, 2)

        assert masks[0][0, 1] and masks[0][1, 0], "colour-0 pixels must be True"
        assert masks[1][0, 2] and masks[1][1, 2], "colour-1 pixels must be True"

    def test_masks_cover_all_foreground_pixels(self):
        from src.separate import masks_from_labels

        rng = np.random.default_rng(0)
        label_map = rng.integers(-1, 4, size=(30, 40), dtype=np.int32)
        masks = masks_from_labels(label_map, 4)

        covered = np.zeros_like(label_map, dtype=bool)
        for m in masks:
            covered |= m
        expected = label_map >= 0
        np.testing.assert_array_equal(covered, expected)

    def test_n_colors_controls_output_length(self):
        from src.separate import masks_from_labels

        label_map = np.zeros((10, 10), dtype=np.int32)
        assert len(masks_from_labels(label_map, 3)) == 3
        assert len(masks_from_labels(label_map, 6)) == 6


class TestCleanMask:
    def test_removes_small_components(self):
        from src.separate import clean_mask

        mask = np.zeros((50, 50), dtype=bool)
        mask[5, 5] = True          # isolated single pixel (area = 1)
        mask[20:30, 20:30] = True  # 10x10 block (area = 100)

        cleaned = clean_mask(mask, min_area_px=10)

        assert not cleaned[5, 5], "single pixel must be removed"
        assert cleaned[25, 25], "10x10 block must survive"

    def test_keeps_components_at_threshold(self):
        from src.separate import clean_mask

        mask = np.zeros((50, 50), dtype=bool)
        mask[10:14, 10:14] = True  # exactly 4x4 = 16 px

        assert clean_mask(mask, min_area_px=16)[12, 12]
        assert not clean_mask(mask, min_area_px=17)[12, 12]


# ══════════════════════════════════════════════════════════════════════════════
# src.vectorize
# ══════════════════════════════════════════════════════════════════════════════

class TestMaskToPolygons:
    def test_circle_returns_single_polygon(self):
        from src.vectorize import mask_to_polygons

        mask = _circle(200, 200, 100, 100, 40)
        multi = mask_to_polygons(mask, simplify_px=1.0)

        assert isinstance(multi, MultiPolygon)
        assert len(multi.geoms) == 1, "filled circle must yield exactly one polygon"

    def test_circle_area_within_tolerance(self):
        """Polygonal approximation must be within 3% of the true disc area."""
        from src.vectorize import mask_to_polygons

        r = 40
        mask = _circle(200, 200, 100, 100, r)
        multi = mask_to_polygons(mask, simplify_px=1.0)
        poly = multi.geoms[0]

        true_area = math.pi * r ** 2
        rel_err = abs(poly.area - true_area) / true_area
        assert rel_err < 0.03, f"area relative error {rel_err:.1%} exceeds 3%"

    def test_empty_mask_returns_empty_multipolygon(self):
        from src.vectorize import mask_to_polygons

        mask = np.zeros((100, 100), dtype=bool)
        multi = mask_to_polygons(mask)

        assert isinstance(multi, MultiPolygon)
        assert len(multi.geoms) == 0

    def test_ring_has_one_polygon_with_hole(self):
        """Donut mask must yield a polygon with exactly one interior ring."""
        from src.vectorize import mask_to_polygons

        mask = _ring(200, 200, 100, 100, r_out=50, r_in=20)
        multi = mask_to_polygons(mask, simplify_px=1.0)

        assert len(multi.geoms) == 1, "donut must yield one polygon"
        poly = multi.geoms[0]
        assert len(poly.interiors) == 1, "polygon must have exactly one hole"

    def test_ring_area_within_tolerance(self):
        """Ring polygon area must match true annulus area within 4%."""
        from src.vectorize import mask_to_polygons

        r_out, r_in = 50, 20
        mask = _ring(200, 200, 100, 100, r_out, r_in)
        multi = mask_to_polygons(mask, simplify_px=1.0)
        poly = multi.geoms[0]

        true_area = math.pi * (r_out ** 2 - r_in ** 2)
        rel_err = abs(poly.area - true_area) / true_area
        assert rel_err < 0.04, f"ring area relative error {rel_err:.1%} exceeds 4%"

    def test_two_disconnected_blobs(self):
        """Two separate filled circles must yield two separate polygons."""
        from src.vectorize import mask_to_polygons

        mask = np.zeros((200, 400), dtype=bool)
        mask |= _circle(200, 400, 100, 80, 30)
        mask |= _circle(200, 400, 100, 300, 30)
        multi = mask_to_polygons(mask, simplify_px=1.0)

        assert len(multi.geoms) == 2


class TestPxToMm:
    def test_scales_area_correctly(self):
        """Area after scaling must equal area_px / px_per_mm²."""
        from src.vectorize import mask_to_polygons, px_to_mm

        r, px_per_mm = 40, 10.0
        mask = _circle(200, 200, 100, 100, r)
        poly_px = mask_to_polygons(mask, simplify_px=1.0).geoms[0]
        poly_mm = px_to_mm(poly_px, px_per_mm)

        expected_area_mm2 = poly_px.area / (px_per_mm ** 2)
        rel_err = abs(poly_mm.area - expected_area_mm2) / expected_area_mm2
        assert rel_err < 1e-9, "area scaling must be exact"

    def test_hole_preserved_after_scaling(self):
        """Interior rings must survive px_to_mm conversion."""
        from src.vectorize import mask_to_polygons, px_to_mm

        mask = _ring(200, 200, 100, 100, 50, 20)
        poly_px = mask_to_polygons(mask, simplify_px=1.0).geoms[0]
        poly_mm = px_to_mm(poly_px, 10.0)

        assert isinstance(poly_mm, Polygon)
        assert len(poly_mm.interiors) == 1


class TestVectorizeMasks:
    def test_filters_by_min_area(self):
        """Polygons smaller than min_area_mm2 must be dropped."""
        from src.vectorize import vectorize_masks

        # 10 px/mm → 1 mm = 10 px; 1 mm² = 100 px²
        # Circle r=4 px → area ≈ 50 px² = 0.5 mm² → should be dropped at 1 mm²
        # Circle r=12 px → area ≈ 452 px² = 4.5 mm² → should survive
        px_per_mm = 10.0
        mask = np.zeros((200, 200), dtype=bool)
        mask |= _circle(200, 200, 50, 50, 4)    # ~50 px²  / 100 = ~0.5 mm²
        mask |= _circle(200, 200, 150, 150, 12)  # ~452 px² / 100 = ~4.5 mm²

        result = vectorize_masks([mask], px_per_mm=px_per_mm, min_area_mm2=1.0)

        assert len(result) == 1
        polys = result[0]
        assert len(polys) == 1, "only the large circle should survive the area filter"
        assert polys[0].area >= 1.0

    def test_output_sorted_by_area_descending(self):
        """Polygons within a colour must be ordered largest-first."""
        from src.vectorize import vectorize_masks

        mask = np.zeros((300, 300), dtype=bool)
        mask |= _circle(300, 300, 150, 150, 40)  # large
        mask |= _circle(300, 300,  50,  50, 15)  # small

        result = vectorize_masks([mask], px_per_mm=10.0, min_area_mm2=0.1)
        polys = result[0]

        assert len(polys) == 2
        assert polys[0].area >= polys[1].area, "largest polygon must come first"

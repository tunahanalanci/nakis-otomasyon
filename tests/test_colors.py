"""Unit tests for colour quantisation (src.colors.quantise)."""

from __future__ import annotations

import numpy as np
import pytest

from src.config import Config


def _cfg(n: int) -> Config:
    return Config(max_colors=n)


def _solid(h: int, w: int, colour: tuple[int, int, int]) -> np.ndarray:
    arr = np.empty((h, w, 3), dtype=np.uint8)
    arr[:] = colour
    return arr


class TestQuantise:
    def test_two_colors_exact(self):
        """Exactly 2 distinct colours -> 2-entry palette, labels {0, 1}."""
        from src.colors import quantise

        img = np.zeros((60, 80, 3), dtype=np.uint8)
        img[:, :40] = [255, 0, 0]   # left: red
        img[:, 40:] = [0, 0, 255]   # right: blue

        label_map, palette = quantise(img, _cfg(2))

        assert len(palette) == 2
        assert set(np.unique(label_map)) == {0, 1}

    def test_four_colors_reduced_to_two(self):
        """4-colour image reduced to max_colors=2 -> exactly 2 clusters."""
        from src.colors import quantise

        img = np.zeros((80, 80, 3), dtype=np.uint8)
        img[:40, :40] = [255,   0,   0]   # red
        img[:40, 40:] = [  0, 255,   0]   # green
        img[40:, :40] = [  0,   0, 255]   # blue
        img[40:, 40:] = [255, 255,   0]   # yellow

        label_map, palette = quantise(img, _cfg(2))

        assert len(palette) == 2
        assert set(np.unique(label_map)) == {0, 1}

    def test_background_pixels_labeled_minus_one(self):
        """RGBA image: transparent pixels (alpha=0) must receive label -1."""
        from src.colors import quantise

        img = np.zeros((60, 80, 4), dtype=np.uint8)
        img[:, :, 3] = 255                  # fully opaque
        img[:, :40, :3] = [255, 0, 0]
        img[:, 40:, :3] = [0, 0, 255]
        img[:10, :, 3] = 0                  # top 10 rows transparent

        label_map, palette = quantise(img, _cfg(2))

        assert np.all(label_map[:10] == -1), "transparent rows must be -1"
        fg = label_map[10:]
        assert set(np.unique(fg)).issubset({0, 1}), "foreground must only be 0 or 1"

    def test_dominant_color_is_palette_zero(self):
        """Largest cluster (3/4 of image) must be palette[0]."""
        from src.colors import quantise

        img = np.zeros((80, 80, 3), dtype=np.uint8)
        img[:60, :] = [220, 20, 20]    # red — dominant (60 rows)
        img[60:, :] = [ 20, 20, 220]   # blue — minority (20 rows)

        _, palette = quantise(img, _cfg(2))

        r, g, b = palette[0]
        # Dominant colour is red: R channel should be substantially larger than B
        assert r > b, f"Expected red-dominant palette[0], got R={r} B={b}"

    def test_single_color_image(self):
        """Single-colour image with max_colors=3 -> 1 cluster, label 0 everywhere."""
        from src.colors import quantise

        img = _solid(40, 40, (128, 64, 32))
        label_map, palette = quantise(img, _cfg(3))

        # KMeans with n_clusters=min(3, n_pixels) may legitimately give 1 if all
        # pixels are identical; what matters is that all labels are the same value
        # and no label is -1.
        assert np.all(label_map >= 0), "no background in opaque RGB image"
        assert len(np.unique(label_map)) == 1, "all pixels must share one label"

    def test_label_map_shape_matches_input(self):
        """label_map must have the same H×W as the input image."""
        from src.colors import quantise

        h, w = 37, 53
        img = np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)
        label_map, _ = quantise(img, _cfg(4))

        assert label_map.shape == (h, w)

    def test_palette_rgb_values_in_range(self):
        """Each palette entry must have R, G, B values in [0, 255]."""
        from src.colors import quantise

        img = np.random.randint(0, 256, (60, 60, 3), dtype=np.uint8)
        _, palette = quantise(img, _cfg(4))

        for r, g, b in palette:
            assert 0 <= r <= 255
            assert 0 <= g <= 255
            assert 0 <= b <= 255

"""Colour quantisation: reduce image palette to at most max_colors using k-means."""

from __future__ import annotations

import numpy as np

from src.config import Config


def quantise(img: np.ndarray, cfg: Config) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    """Run k-means on *img* pixels and return (label_map, palette).

    *label_map* is an HxW int array where each value is a palette index.
    *palette* is an ordered list of (R, G, B) tuples, background colour last.

    TODO: flatten to 1-D pixel list and run sklearn KMeans with cfg.max_colors.
    TODO: sort palette by estimated coverage (largest cluster first).
    TODO: detect and mark the background colour so it is stitched last (or skipped).
    TODO: expose random_state in Config for reproducibility.
    """
    raise NotImplementedError


def build_color_report(palette: list[tuple[int, int, int]], out_path) -> None:
    """Write a human-readable colour-order report to *out_path*.

    DST carries no colour data; the operator must change thread in the order listed here.

    TODO: include colour index, RGB value, nearest Madeira/Robison-Anton thread name.
    TODO: write both .txt and a small PNG swatch sheet.
    """
    raise NotImplementedError

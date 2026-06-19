"""Colour separation: produce a boolean binary mask per palette entry."""

from __future__ import annotations

import cv2
import numpy as np


def masks_from_labels(
    label_map: np.ndarray,
    n_colors: int,
) -> list[np.ndarray]:
    """Return one boolean HxW mask per colour index in *label_map*.

    Background pixels (label == -1) are False in every mask.
    Mask order matches the palette order from :mod:`src.colors`
    (index 0 = dominant colour).

    Parameters
    ----------
    label_map : HxW int32 array as returned by :func:`src.colors.quantise`.
    n_colors  : number of colour entries in the palette.
    """
    return [label_map == i for i in range(n_colors)]


def clean_mask(mask: np.ndarray, min_area_px: int = 50) -> np.ndarray:
    """Remove foreground connected components whose area < *min_area_px*.

    Uses 8-connectivity so diagonally-touching blobs are one component.
    Returns a cleaned boolean HxW mask.

    Parameters
    ----------
    mask        : boolean or uint8 HxW array.
    min_area_px : components smaller than this pixel count are discarded.
                  Derive from Config: round((min_stitch_mm * px_per_mm) ** 2).
    """
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    cleaned = np.zeros(mask.shape, dtype=bool)
    for label in range(1, n_labels):        # label 0 = OpenCV background
        if stats[label, cv2.CC_STAT_AREA] >= min_area_px:
            cleaned[labels == label] = True
    return cleaned

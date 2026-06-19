"""Colour separation: produce a binary mask per palette entry."""

from __future__ import annotations

import numpy as np


def masks_from_labels(label_map: np.ndarray, n_colors: int) -> list[np.ndarray]:
    """Return one boolean HxW mask per colour index in *label_map*.

    Mask order matches the palette order from :mod:`src.colors`.

    TODO: optionally merge thin isolated islands into neighbouring colour regions.
    TODO: apply morphological closing to fill small holes inside each mask.
    """
    raise NotImplementedError


def clean_mask(mask: np.ndarray, min_area_px: int = 50) -> np.ndarray:
    """Remove connected components smaller than *min_area_px* from *mask*.

    TODO: use cv2.connectedComponentsWithStats for component labelling.
    TODO: expose min_area_px through Config (derived from min_stitch_mm).
    """
    raise NotImplementedError

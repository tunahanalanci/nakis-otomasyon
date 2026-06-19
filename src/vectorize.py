"""Raster-to-vector: convert binary masks to Shapely polygons."""

from __future__ import annotations

import numpy as np
from shapely.geometry import MultiPolygon, Polygon


def mask_to_polygons(mask: np.ndarray, simplify_px: float = 1.0) -> MultiPolygon:
    """Trace contours in *mask* and return a :class:`~shapely.geometry.MultiPolygon`.

    Uses OpenCV findContours internally; holes become interior rings.

    TODO: call cv2.findContours with RETR_CCOMP to capture parent/hole hierarchy.
    TODO: convert pixel contours to Shapely Polygon objects with correct holes.
    TODO: apply Douglas-Peucker simplification (simplify_px tolerance).
    TODO: convert pixel coordinates to mm using the px-per-mm scale factor.
    """
    raise NotImplementedError


def px_to_mm(polygon: Polygon, px_per_mm: float) -> Polygon:
    """Scale *polygon* coordinates from pixels to millimetres.

    TODO: apply affine scaling via shapely.affinity.scale.
    """
    raise NotImplementedError

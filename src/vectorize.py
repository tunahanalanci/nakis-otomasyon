"""Raster-to-vector: convert binary masks to Shapely polygons in mm coordinates."""

from __future__ import annotations

import cv2
import numpy as np
from shapely.affinity import scale as shp_scale, translate as shp_translate
from shapely.geometry import MultiPolygon, Polygon


def mask_to_polygons(
    mask: np.ndarray,
    simplify_px: float = 1.0,
) -> MultiPolygon:
    """Trace contours in *mask* and return a :class:`~shapely.geometry.MultiPolygon`.

    Uses ``RETR_CCOMP`` so that outer boundaries and their direct holes are
    captured in a two-level hierarchy.  Each outer contour becomes a Shapely
    Polygon; its child contours become interior rings (holes).

    Coordinates are in **pixel** units.  Call :func:`px_to_mm` afterwards to
    obtain millimetre coordinates.

    Parameters
    ----------
    mask        : boolean or uint8 HxW binary mask (non-zero = foreground).
    simplify_px : Douglas-Peucker epsilon in pixels for :func:`cv2.approxPolyDP`.
                  Larger values produce fewer vertices.
    """
    contours, hierarchy = cv2.findContours(
        mask.astype(np.uint8),
        cv2.RETR_CCOMP,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    if hierarchy is None or len(contours) == 0:
        return MultiPolygon()

    hier = hierarchy[0]   # (N, 4): [Next, Prev, First_Child, Parent]

    polygons: list[Polygon] = []

    for i, contour in enumerate(contours):
        # Skip hole contours — they are collected when processing their parent
        if hier[i][3] != -1:
            continue

        exterior = _approx_pts(contour, simplify_px)
        if len(exterior) < 3:
            continue

        # Collect all direct-child contours as holes
        holes: list[np.ndarray] = []
        for j, child in enumerate(contours):
            if hier[j][3] == i:
                hole_pts = _approx_pts(child, simplify_px)
                if len(hole_pts) >= 3:
                    holes.append(hole_pts)

        try:
            poly = Polygon(exterior, holes)
        except Exception:
            continue

        # Attempt to repair self-intersections (e.g. figure-eight artefacts)
        if not poly.is_valid:
            poly = poly.buffer(0)

        if isinstance(poly, Polygon) and poly.area > 0:
            polygons.append(poly)
        elif isinstance(poly, MultiPolygon):
            polygons.extend(p for p in poly.geoms if p.area > 0)

    return MultiPolygon(polygons)


def px_to_mm(geom: Polygon, px_per_mm: float, img_h_px: float = 0) -> Polygon:
    """Scale *geom* from pixel coordinates to millimetres, flipping Y once.

    Image pixel space has Y increasing downward (y=0 at top).
    Embroidery / DST space uses Y increasing upward (mathematical convention).
    This function applies the single authoritative Y flip:

        x_mm = x_px / px_per_mm
        y_mm = (img_h_px - y_px) / px_per_mm

    so that downstream code (fill, export, preview) all operate in the same
    "Y up" coordinate system and the preview render_preview flip is correct.

    Parameters
    ----------
    geom      : Polygon in pixel coordinates.
    px_per_mm : pixels-per-millimetre of the source image.
    img_h_px  : total image height in pixels (required for Y flip).
                When 0, falls back to the old (no-flip) behaviour.
    """
    factor = 1.0 / px_per_mm
    if img_h_px > 0:
        # Flip Y: scale with yfact=-factor (reflects around y=0), then
        # translate up by img_h_mm so values land in [0, img_h_mm].
        img_h_mm = img_h_px * factor
        flipped  = shp_scale(geom, xfact=factor, yfact=-factor, origin=(0, 0))
        return shp_translate(flipped, xoff=0, yoff=img_h_mm)
    return shp_scale(geom, xfact=factor, yfact=factor, origin=(0, 0))


def vectorize_masks(
    masks: list[np.ndarray],
    px_per_mm: float,
    simplify_px: float = 1.0,
    min_area_mm2: float = 1.0,
) -> list[list[Polygon]]:
    """Convert per-colour binary masks to lists of Shapely Polygons in mm.

    For each colour mask:
      1. Trace contours with :func:`mask_to_polygons` (pixel coords).
      2. Convert each polygon to mm with :func:`px_to_mm`.
      3. Discard polygons whose mm² area < *min_area_mm2*
         (too small to stitch meaningfully).

    Parameters
    ----------
    masks       : list of boolean HxW arrays, one per colour (from
                  :func:`src.separate.masks_from_labels`).
    px_per_mm   : pixels-per-millimetre from :func:`src.preprocess.load_and_scale`.
    simplify_px : Douglas-Peucker epsilon forwarded to :func:`mask_to_polygons`.
    min_area_mm2: polygons smaller than this are dropped (default: 1 mm²).

    Returns
    -------
    A list (one entry per colour) of :class:`~shapely.geometry.Polygon` lists
    in millimetre coordinates, ordered by area descending within each colour.
    """
    result: list[list[Polygon]] = []

    img_h_px = masks[0].shape[0] if masks else 0

    for mask in masks:
        multi    = mask_to_polygons(mask, simplify_px)
        polys_mm = [
            px_to_mm(p, px_per_mm, img_h_px)
            for p in multi.geoms
            if px_to_mm(p, px_per_mm, img_h_px).area >= min_area_mm2
        ]
        # Largest area first so stitch engine processes dominant shapes first
        polys_mm.sort(key=lambda p: p.area, reverse=True)
        result.append(polys_mm)

    return result


# ── Private helpers ────────────────────────────────────────────────────────────

def _approx_pts(contour: np.ndarray, epsilon: float) -> np.ndarray:
    """Return an (N, 2) int array of simplified contour vertices."""
    approx = cv2.approxPolyDP(contour, epsilon, closed=True)
    return approx[:, 0, :]   # (N, 1, 2) → (N, 2)

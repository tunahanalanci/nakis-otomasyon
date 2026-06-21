"""Image pre-processing: background masking, mm-to-px scaling, and denoising."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from src.config import Config

# ── Module-level constants ────────────────────────────────────────────────────
MIN_PX_PER_MM: float = 16.0  # minimum output resolution
ALPHA_THRESH:  int   = 128   # alpha < this → background
MEDIAN_KSIZE:  int   = 3     # median blur kernel size (must be odd)
BG_BRIGHT_THRESH: int = 240  # RGB pixels with all channels > this = near-white background


def load_and_scale(
    png_path: str | Path,
    cfg: Config,
) -> tuple[np.ndarray, float]:
    """Load a PNG, mask the background, scale to the target mm size, and denoise.

    Orchestrates: load → remove_background → resize → denoise → _clean_mask.

    Returns
    -------
    img_rgba  : HxWx4 uint8 array.  Alpha encodes foreground:
                255 = stitch this pixel, 0 = background / skip.
    px_per_mm : pixels-per-millimetre of the returned image.
    """
    # ── Load ──────────────────────────────────────────────────────────────────
    img_pil  = Image.open(str(png_path)).convert("RGBA")
    orig_w, _ = img_pil.size
    arr_rgba = np.asarray(img_pil, dtype=np.uint8)   # HxWx4, possibly read-only

    # ── Background mask (on original resolution, before resize) ───────────────
    fg_mask = remove_background(arr_rgba)             # HxW bool

    # ── Target pixel dimensions ───────────────────────────────────────────────
    px_per_mm = max(MIN_PX_PER_MM, orig_w / cfg.width_mm)
    target_w  = max(1, round(cfg.width_mm  * px_per_mm))
    target_h  = max(1, round(cfg.height_mm * px_per_mm))

    # ── Resize RGB and mask separately ───────────────────────────────────────
    # fromarray infers mode from array shape: HxWx3 uint8 → RGB, HxW uint8 → L
    rgb_resized = np.asarray(
        Image.fromarray(arr_rgba[:, :, :3]).resize(
            (target_w, target_h), Image.LANCZOS
        ),
        dtype=np.uint8,
    )
    # NEAREST keeps the binary mask crisp (no anti-aliasing artefacts)
    mask_resized = np.asarray(
        Image.fromarray(fg_mask.astype(np.uint8) * 255).resize(
            (target_w, target_h), Image.NEAREST
        ),
        dtype=np.uint8,
    )

    # ── Denoise RGB ───────────────────────────────────────────────────────────
    rgb_denoised = denoise(rgb_resized)

    # ── Remove isolated pixel islands from the foreground mask ────────────────
    min_area_px = max(4, round((cfg.min_stitch_mm * px_per_mm) ** 2))
    fg_clean    = _clean_mask(mask_resized > 127, min_area_px)

    # ── Assemble RGBA output ──────────────────────────────────────────────────
    alpha = (fg_clean.astype(np.uint8)) * 255
    out   = np.dstack([rgb_denoised, alpha])
    return out, px_per_mm


def remove_background(img_rgba: np.ndarray) -> np.ndarray:
    """Return a HxW boolean foreground mask (True = stitch this pixel).

    When the PNG carries a real alpha channel (any pixel alpha < ALPHA_THRESH),
    the alpha channel is used directly.  Otherwise every pixel is foreground.

    TODO: flood-fill corner-based removal for opaque images (solid background).
    TODO: GrabCut fallback for complex / gradient backgrounds.
    """
    alpha = img_rgba[:, :, 3]
    if int(alpha.min()) < ALPHA_THRESH:
        return alpha >= ALPHA_THRESH
    # Opaque image — detect near-white background by brightness threshold.
    rgb = img_rgba[:, :, :3]
    near_white = np.all(rgb > BG_BRIGHT_THRESH, axis=2)
    return ~near_white


def denoise(img: np.ndarray) -> np.ndarray:
    """Apply a median blur to suppress isolated pixel noise.

    Accepts HxWx3 (RGB) or HxWx1 (grey) uint8 arrays.  MEDIAN_KSIZE=3 is
    gentle enough to preserve colour boundaries while removing single-pixel
    compression or camera artefacts.
    """
    return cv2.medianBlur(np.ascontiguousarray(img), MEDIAN_KSIZE)


# ── Private helpers ────────────────────────────────────────────────────────────

def _clean_mask(mask: np.ndarray, min_area_px: int) -> np.ndarray:
    """Remove foreground connected components whose pixel area < min_area_px.

    Uses 8-connectivity so diagonal blobs count as one component.
    Returns a cleaned HxW boolean mask.
    """
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    cleaned = np.zeros(mask.shape, dtype=bool)
    for label in range(1, n_labels):          # label 0 = background in OpenCV
        if stats[label, cv2.CC_STAT_AREA] >= min_area_px:
            cleaned[labels == label] = True
    return cleaned

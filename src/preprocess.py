"""Image pre-processing: background removal, alpha flattening, and mm-to-px scaling."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from src.config import Config


def load_and_scale(png_path: str | Path, cfg: Config) -> np.ndarray:
    """Load *png_path*, flatten alpha onto white, and resize to target mm dimensions.

    Returns an HxWx3 uint8 RGB array at the DPI implied by the mm/px mapping.

    TODO: detect transparent background vs. solid background automatically.
    TODO: compute DPI from cfg.width_mm / cfg.height_mm and apply correct aspect ratio.
    TODO: add optional smart-crop to remove uniform border before scaling.
    """
    raise NotImplementedError


def remove_background(img: np.ndarray) -> np.ndarray:
    """Remove or flatten the image background, returning an RGBA array.

    TODO: flood-fill corner-based removal for solid backgrounds.
    TODO: GrabCut-based removal for complex backgrounds (opencv).
    TODO: honour an alpha channel that is already present in the source.
    """
    raise NotImplementedError


def denoise(img: np.ndarray) -> np.ndarray:
    """Apply mild denoising to reduce artefacts before colour quantisation.

    TODO: bilateral filter (preserves edges) via cv2.bilateralFilter.
    TODO: expose filter strength through Config.
    """
    raise NotImplementedError

"""Top-level pipeline: orchestrates all stages from PNG to DST output."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from src.config import Config
from src.preprocess import load_and_scale
from src.colors import quantise, build_color_report


def run(
    png_path: str | Path,
    cfg: Config,
    out_dir: str | Path,
    *,
    debug: bool = False,
) -> Path:
    """Execute the full PNG -> DST pipeline and return the path to the DST file.

    Stages 1-2 are implemented.  Stages 3-10 raise NotImplementedError.

    Parameters
    ----------
    png_path : path to the input PNG file.
    cfg      : pipeline configuration.
    out_dir  : directory for all output artefacts.
    debug    : when True, save intermediate artefacts (colour-reduced PNG,
               colour-order report) to out_dir before raising.
    """
    out_dir  = Path(out_dir)
    png_path = Path(png_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = png_path.stem

    # ── Stage 1: Preprocess ───────────────────────────────────────────────────
    img_rgba, px_per_mm = load_and_scale(png_path, cfg)

    # ── Stage 2: Colour quantisation ─────────────────────────────────────────
    label_map, palette = quantise(img_rgba, cfg)

    if debug:
        _save_quantised_png(
            label_map, palette,
            out_dir / f"{stem}_debug_colors.png",
        )
        build_color_report(palette, out_dir / f"{stem}_color_report")

    # ── Stages 3-10: not yet implemented ─────────────────────────────────────
    # TODO: stage 3  — src.separate.masks_from_labels + clean_mask
    # TODO: stage 4  — src.vectorize.mask_to_polygons + px_to_mm
    # TODO: stage 5  — stitch generation (fill / satin / running + underlay)
    # TODO: stage 6  — src.optimize.order_colors + insert_trims + minimize_jumps
    # TODO: stage 7  — src.export_dst.export
    # TODO: stage 8  — src.validate.validate + render_preview
    # TODO: stage 9  — src.usb_writer (optional)
    raise NotImplementedError("Pipeline stages 3-10 not yet implemented.")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _save_quantised_png(
    label_map: np.ndarray,
    palette: list[tuple[int, int, int]],
    path: Path,
) -> None:
    """Paint each label with its palette colour; background stays white."""
    h, w   = label_map.shape
    rgb    = np.full((h, w, 3), 255, dtype=np.uint8)
    for idx, colour in enumerate(palette):
        rgb[label_map == idx] = colour
    Image.fromarray(rgb, "RGB").save(str(path))

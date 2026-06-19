"""Top-level pipeline: orchestrates all stages from PNG to DST output."""

from __future__ import annotations

from pathlib import Path

from src.config import Config


def run(png_path: str | Path, cfg: Config, out_dir: str | Path) -> Path:
    """Execute the full PNG → DST pipeline and return the path to the output DST file.

    Stages (each stage is a TODO until its module is implemented):

    1. Preprocess  — load, scale, background removal, denoise
    2. Colours     — k-means quantisation, build palette, colour report
    3. Separate    — per-colour binary masks
    4. Vectorize   — masks → Shapely polygons (px → mm)
    5. Stitch gen  — fill / satin / running + underlay per polygon
    6. Optimise    — colour ordering, jump minimisation, trim insertion
    7. Export      — write DST via pyembroidery
    8. Validate    — bounds, density, stitch count checks
    9. Preview     — render preview PNG
    10. USB write  — copy artefacts to USB (optional)

    TODO: wire stage 1 (src.preprocess.load_and_scale + remove_background + denoise).
    TODO: wire stage 2 (src.colors.quantise + build_color_report).
    TODO: wire stage 3 (src.separate.masks_from_labels + clean_mask).
    TODO: wire stage 4 (src.vectorize.mask_to_polygons + px_to_mm).
    TODO: wire stage 5 — choose satin vs fill per polygon using satin.width_at().
    TODO: wire stage 6 (src.optimize.order_colors + insert_trims + minimize_jumps).
    TODO: wire stage 7 (src.export_dst.export).
    TODO: wire stage 8 (src.validate.validate) and surface errors to caller.
    TODO: wire stage 9 (src.validate.render_preview).
    TODO: optionally wire stage 10 (src.usb_writer.find_usb + write_to_usb).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dst_path = out_dir / (Path(png_path).stem + ".dst")

    raise NotImplementedError("Pipeline stages not yet implemented — see TODO list above.")

"""Top-level pipeline: orchestrates all stages from PNG to DST output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from src.colors import build_color_report, quantise
from src.config import Config
from src.export_dst import ExportStats, export as _export_dst
from src.optimize import StitchBlock, optimize
from src.preprocess import load_and_scale
from src.separate import clean_mask, masks_from_labels
from src.validate import ValidationReport, render_preview, validate
from src.vectorize import vectorize_masks

# Target stitch length for fill segments.  Spacing controls row density;
# this controls how far apart stitches are *along* each row.
_FILL_STITCH_MM: float = 3.0


@dataclass
class PipelineResult:
    """All output artefacts and statistics produced by a pipeline run."""

    dst_path:          Path
    preview_path:      Path
    color_report_path: Path
    total_stitches:    int
    n_color_blocks:    int
    bounds_mm:         tuple[float, float, float, float]  # minx miny maxx maxy
    validation:        ValidationReport


def run(
    png_path: str | Path,
    cfg: Config,
    out_dir: str | Path,
    *,
    debug: bool = False,
    usb_path: str | Path | None = None,
    usb_layout: str = "root",
) -> PipelineResult:
    """Run the complete PNG → DST pipeline.

    Stages
    ------
    1.  Preprocess  — resize to *cfg.width_mm / cfg.height_mm*, denoise.
    2.  Quantise    — k-means colour reduction to *cfg.max_colors* colours.
    3.  Separate    — one binary mask per colour; remove noise islands.
    4.  Vectorise   — contour-trace each mask to Shapely polygons (mm).
    5.  Stitch      — tatami fill (with underlay) or satin per polygon.
    6.  Optimise    — nearest-neighbour colour ordering; filter short stitches.
    7.  Export DST  — write Tajima DST + ``renk_sirasi.txt``.
    8.  Validate    — hoop, density, length checks; render preview PNG.
    9.  USB (opt.)  — copy artefacts to *usb_path* if provided.

    Parameters
    ----------
    png_path   : input PNG file.
    cfg        : pipeline configuration.
    out_dir    : directory for all output artefacts.
    debug      : if True, also save colour-reduced PNG and thread-swatch PNG.
    usb_path   : optional USB drive root; when given, DST + report + preview
                 are copied there according to *usb_layout*.
    usb_layout : ``"root"`` copies directly to USB root; any other string
                 names a subdirectory (see ``usb_writer.write_to_usb``).
    """
    out_dir  = Path(out_dir)
    png_path = Path(png_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = png_path.stem

    # ── 1. Preprocess ─────────────────────────────────────────────────────────
    img_rgba, px_per_mm = load_and_scale(png_path, cfg)

    # ── 2. Colour quantisation ────────────────────────────────────────────────
    label_map, palette = quantise(img_rgba, cfg)

    if debug:
        _save_quantised_png(label_map, palette,
                            out_dir / f"{stem}_debug_colors.png")
        build_color_report(palette, out_dir / f"{stem}_color_report")

    # ── 3. Separate — one mask per colour ─────────────────────────────────────
    raw_masks = masks_from_labels(label_map, len(palette))
    masks     = [clean_mask(m) for m in raw_masks]

    # ── 4. Vectorise — polygons in mm ─────────────────────────────────────────
    polygons_by_color = vectorize_masks(masks, px_per_mm, min_area_mm2=1.0)

    # ── 5. Stitch generation ──────────────────────────────────────────────────
    blocks = _generate_blocks(polygons_by_color, cfg)

    # ── 6. Optimise ───────────────────────────────────────────────────────────
    blocks = optimize(blocks, cfg)

    # ── 7. Export DST ─────────────────────────────────────────────────────────
    export_stats: ExportStats = _export_dst(blocks, palette, cfg, out_dir, stem=stem)
    color_report_path = out_dir / "renk_sirasi.txt"

    # ── 8. Validate + preview ─────────────────────────────────────────────────
    validation    = validate(export_stats.dst_path, cfg)
    preview_path  = render_preview(
        export_stats.dst_path,
        out_dir / f"{stem}_preview.png",
    )

    # ── 9. Optional USB copy ──────────────────────────────────────────────────
    if usb_path is not None:
        from src.usb_writer import write_to_usb  # noqa: PLC0415
        write_to_usb(
            export_stats.dst_path,
            color_report_path,
            usb_path,
            preview_path=preview_path,
            layout=usb_layout,
        )

    return PipelineResult(
        dst_path          = export_stats.dst_path,
        preview_path      = preview_path,
        color_report_path = color_report_path,
        total_stitches    = export_stats.total_stitches,
        n_color_blocks    = export_stats.n_color_blocks,
        bounds_mm         = export_stats.bounds_mm,
        validation        = validation,
    )


# ── Private helpers ────────────────────────────────────────────────────────────

def _generate_blocks(
    polygons_by_color: list[list],
    cfg: Config,
) -> list[StitchBlock]:
    """Generate StitchBlocks for every polygon in every colour.

    Selection logic per polygon:
    * Try satin — accepted when width falls within [satin.min_width_mm,
      satin.max_width_mm] (``satin.generate`` returns [] otherwise).
    * Fall back to fill (tatami) with underlay if *cfg.fill.underlay* is set.
    """
    from src.stitch.fill  import generate as _fill   # noqa: PLC0415
    from src.stitch.satin import generate as _satin  # noqa: PLC0415

    blocks: list[StitchBlock] = []

    for color_idx, polys in enumerate(polygons_by_color):
        for poly in polys:
            if poly.is_empty or not poly.is_valid:
                continue

            pts = _satin(poly, cfg.satin)
            if not pts:
                pts = _fill(
                    poly, cfg.fill,
                    stitch_mm            = _FILL_STITCH_MM,
                    pull_compensation_mm = cfg.pull_compensation_mm,
                )

            if pts:
                blocks.append(StitchBlock(color_idx=color_idx, points=pts))

    return blocks


def _save_quantised_png(
    label_map: np.ndarray,
    palette: list[tuple[int, int, int]],
    path: Path,
) -> None:
    """Paint each label with its palette colour; background stays white."""
    h, w = label_map.shape
    rgb  = np.full((h, w, 3), 255, dtype=np.uint8)
    for idx, colour in enumerate(palette):
        rgb[label_map == idx] = colour
    Image.fromarray(rgb).save(str(path))

"""Top-level pipeline: orchestrates all stages from PNG to DST output.

Active engine: Ink/Stitch (use_inkstitch=True in Config).
Legacy engine path kept in legacy/ for reference.
"""

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
from src.threads import match_palette, write_color_report
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
    palette:           list[tuple[int, int, int]]
    blocks:            list[StitchBlock]   # stitch data in Y-down mm (for render/animation)
    svg_path:          Path | None = None  # Ink/Stitch-compatible SVG for manual editing


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

    # ── 4. Thread matching (Lab color distance) ───────────────────────────────
    thread_matches = match_palette(palette, cfg.thread_brand)

    if cfg.use_inkstitch:
        return _run_inkstitch(
            stem, png_path, out_dir, cfg,
            masks, palette, thread_matches, px_per_mm, usb_path, usb_layout,
        )

    # ── Legacy path ───────────────────────────────────────────────────────────
    polygons_by_color = vectorize_masks(masks, px_per_mm, simplify_px=0.5, min_area_mm2=0.5)
    blocks = _generate_blocks(polygons_by_color, cfg, px_per_mm)
    blocks = optimize(blocks, cfg)
    export_stats: ExportStats = _export_dst(blocks, palette, cfg, out_dir, stem=stem)
    color_report_path = out_dir / "renk_sirasi.txt"
    write_color_report(thread_matches, color_report_path)
    validation   = validate(export_stats.dst_path, cfg)
    preview_path = render_preview(blocks, palette, out_dir / f"{stem}_preview.png")

    # ── SVG for manual editing in Inkscape + Ink/Stitch ───────────────────────
    svg_path: Path | None = None
    try:
        from src.inkstitch_engine import build_svg  # noqa: PLC0415
        svg_path = out_dir / f"{stem}.svg"
        build_svg(masks, thread_matches, px_per_mm,
                  cfg.width_mm, cfg.height_mm, cfg, svg_path)
    except Exception:
        svg_path = None

    if usb_path is not None:
        from src.usb_writer import write_to_usb  # noqa: PLC0415
        write_to_usb(export_stats.dst_path, color_report_path, usb_path,
                     preview_path=preview_path, layout=usb_layout)

    return PipelineResult(
        dst_path          = export_stats.dst_path,
        preview_path      = preview_path,
        color_report_path = color_report_path,
        total_stitches    = export_stats.total_stitches,
        n_color_blocks    = export_stats.n_color_blocks,
        bounds_mm         = export_stats.bounds_mm,
        validation        = validation,
        palette           = palette,
        blocks            = blocks,
        svg_path          = svg_path,
    )


def _run_inkstitch(
    stem, png_path, out_dir, cfg,
    masks, palette, thread_matches, px_per_mm, usb_path, usb_layout,
):
    """Ink/Stitch engine path: SVG → headless Inkscape → DST."""
    from src.inkstitch_engine import build_svg, export_dst, render_dst_preview  # noqa

    svg_path     = out_dir / f"{stem}.svg"
    dst_path     = out_dir / f"{stem}.dst"
    preview_path = out_dir / f"{stem}_preview.png"
    report_path  = out_dir / "renk_sirasi.txt"

    stitch_summary = build_svg(
        masks, thread_matches, px_per_mm,
        cfg.width_mm, cfg.height_mm, cfg,
        svg_path,
    )

    ok = export_dst(svg_path, dst_path)
    if not ok:
        raise RuntimeError(f"Ink/Stitch DST export basarisiz: {dst_path}")

    write_color_report(thread_matches, report_path)
    render_dst_preview(dst_path, thread_matches, preview_path)

    import pyembroidery
    pat = pyembroidery.read(str(dst_path))
    stitch_pts = [s for s in pat.stitches if s[2] == pyembroidery.STITCH]
    cc = [s for s in pat.stitches if s[2] == pyembroidery.COLOR_CHANGE]
    xs = [s[0] for s in stitch_pts] or [0]
    ys = [s[1] for s in stitch_pts] or [0]

    validation = validate(dst_path, cfg)

    if usb_path is not None:
        from src.usb_writer import write_to_usb  # noqa: PLC0415
        write_to_usb(dst_path, report_path, usb_path,
                     preview_path=preview_path, layout=usb_layout)

    return PipelineResult(
        dst_path          = dst_path,
        preview_path      = preview_path,
        color_report_path = report_path,
        total_stitches    = len(stitch_pts),
        n_color_blocks    = len(cc) + 1,
        bounds_mm         = (min(xs)/10, min(ys)/10, max(xs)/10, max(ys)/10),
        validation        = validation,
        palette           = palette,
        blocks            = [],   # Ink/Stitch engine; blok listesi DST'den
        svg_path          = svg_path,
    )


# ── Private helpers ────────────────────────────────────────────────────────────

def _generate_blocks(
    polygons_by_color: list[list],
    cfg: Config,
    px_per_mm: float = 10.0,
) -> list[StitchBlock]:
    """Generate StitchBlocks for every polygon in every colour.

    Stitch type is chosen per-polygon using distance-transform stroke width:
    * width < cfg.running_max_width_mm → running stitch (outline trace)
    * width < cfg.satin_max_width_mm   → satin stitch, fallback fill
    * else                             → tatami fill with underlay
    """
    from src.stitch.fill    import generate as _fill    # noqa: PLC0415
    from src.stitch.running import generate_outline as _running  # noqa: PLC0415
    from src.stitch.satin   import generate as _satin, width_at as _mbr_width  # noqa: PLC0415
    from dataclasses import replace as _dc_replace

    # Satin config with relaxed width gate; DT routing already screened shape size.
    wide_satin_cfg = _dc_replace(cfg.satin, min_width_mm=0.0, max_width_mm=50.0)
    # Half-spacing fill for complex thin shapes (curves, C-arcs) where satin zigzags poorly.
    tight_fill_cfg = _dc_replace(cfg.fill, spacing_mm=max(0.15, cfg.fill.spacing_mm * 0.5))

    blocks: list[StitchBlock] = []

    for color_idx, polys in enumerate(polygons_by_color):
        for poly in polys:
            if poly.is_empty or not poly.is_valid:
                continue

            w_mm  = _stroke_width_mm(poly)          # inscribed-circle diameter
            mbr_w = _mbr_width(poly)                # MBR short side (bounding box)

            if w_mm < cfg.running_max_width_mm:
                pts = _running(poly, cfg)
            elif w_mm < cfg.satin_max_width_mm:
                if mbr_w < cfg.satin_max_width_mm:
                    # Simple elongated shape (l, i, t stems): MBR confirms narrow → satin
                    pts = _satin(poly, wide_satin_cfg)
                    if not pts:
                        pts = _fill(poly, tight_fill_cfg,
                                    stitch_mm=_FILL_STITCH_MM,
                                    pull_compensation_mm=cfg.pull_compensation_mm)
                else:
                    # Complex curve (G arc, e bowl): DT thin but MBR wide → tight fill
                    pts = _fill(poly, tight_fill_cfg,
                                stitch_mm=_FILL_STITCH_MM,
                                pull_compensation_mm=cfg.pull_compensation_mm)
            else:
                pts = _fill(poly, cfg.fill,
                            stitch_mm=_FILL_STITCH_MM,
                            pull_compensation_mm=cfg.pull_compensation_mm)

            if pts:
                blocks.append(StitchBlock(color_idx=color_idx, points=pts))

    return blocks


def _stroke_width_mm(poly) -> float:
    """Distance-transform estimate of stroke width: diameter of largest inscribed circle.

    Rasterises *poly* at 10 px/mm (sufficient to distinguish 0.3–10 mm range),
    fills holes, runs OpenCV distanceTransform, returns 2 × max_radius_mm.
    """
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    _R = 10.0  # raster resolution for width estimation
    ext = np.array(poly.exterior.coords, dtype=np.float64)
    px = np.round(ext * _R).astype(np.int32)
    x0, y0 = int(px[:, 0].min()), int(px[:, 1].min())
    pad = 2
    px -= [x0 - pad, y0 - pad]
    W = int(px[:, 0].max()) + pad + 1
    H = int(px[:, 1].max()) + pad + 1
    if W < 1 or H < 1:
        return 0.0
    canvas = np.zeros((H, W), dtype=np.uint8)
    cv2.fillPoly(canvas, [px.reshape(-1, 1, 2)], 255)
    for ring in poly.interiors:
        hole = np.round(np.array(ring.coords, dtype=np.float64) * _R).astype(np.int32)
        hole -= [x0 - pad, y0 - pad]
        cv2.fillPoly(canvas, [hole.reshape(-1, 1, 2)], 0)
    dist = cv2.distanceTransform(canvas, cv2.DIST_L2, 5)
    r = float(np.max(dist))
    return 2.0 * r / _R if r > 0 else 0.0


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

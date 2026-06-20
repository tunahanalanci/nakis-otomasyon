"""Ink/Stitch based embroidery engine.

Replaces the hand-written stitch generator for the active pipeline path.
Responsibilities:
  1. Per-contour width estimation → automatic stitch type selection
  2. SVG generation with correct Ink/Stitch attributes per element
  3. Headless Inkscape → DST export
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np

from src.config import Config
from src.threads import ThreadMatch

INKSCAPE = r"C:\Program Files\Inkscape\bin\inkscape.exe"

# Ink/Stitch fill underlay attributes (improves coverage on fabric)
_UNDERLAY_ATTRS = (
    ' inkstitch:fill_underlay="true"'
    ' inkstitch:fill_underlay_angle="-45"'
    ' inkstitch:fill_underlay_row_spacing_mm="1.5"'
)


# ── Width estimation ──────────────────────────────────────────────────────────

def estimate_contour_width_mm(cnt: np.ndarray, px_per_mm: float) -> float:
    """Estimate the typical width of a contour polygon in mm.

    Method: distance transform of the rasterised contour.
    max(distanceTransform) = radius of largest inscribed circle → width = 2×.
    A 1-pixel border ensures border pixels are always background (0),
    so distanceTransform has a finite reference point even for solid shapes.
    """
    x, y, w, h = cv2.boundingRect(cnt)
    if w < 1 or h < 1:
        return 0.0
    # +2 border so the filled shape never touches the array edge
    pad = 2
    local = np.zeros((h + 2 * pad, w + 2 * pad), dtype=np.uint8)
    pts = cnt.reshape(-1, 2) - np.array([x - pad, y - pad])
    cv2.fillPoly(local, [pts.astype(np.int32)], 255)
    dist = cv2.distanceTransform(local, cv2.DIST_L2, 5)
    max_radius_px = float(np.max(dist))
    if not np.isfinite(max_radius_px) or max_radius_px <= 0:
        return float(min(w, h)) / px_per_mm  # fallback: bounding box short side
    return 2.0 * max_radius_px / px_per_mm


def choose_stitch_type(width_mm: float, cfg: Config) -> str:
    """Map contour width → Ink/Stitch fill method string.

    Thresholds (config-driven):
      width < running_max_width_mm  → running_stitch  (too thin for fill)
      width < satin_max_width_mm    → contour_fill    (satin-like)
      else                          → auto_fill       (tatami fill)
    """
    if width_mm < cfg.running_max_width_mm:
        return "running_stitch"
    if width_mm < cfg.satin_max_width_mm:
        return "contour_fill"
    return "auto_fill"


# ── SVG path helpers ──────────────────────────────────────────────────────────

def _contour_to_path(cnt: np.ndarray, px_per_mm: float) -> str:
    pts = cnt.reshape(-1, 2)
    if len(pts) < 2:
        return ""
    f = 1.0 / px_per_mm
    parts = [f"M {pts[0][0]*f:.3f},{pts[0][1]*f:.3f}"]
    for px, py in pts[1:]:
        parts.append(f"L {px*f:.3f},{py*f:.3f}")
    parts.append("Z")
    return " ".join(parts)


def _svg_element(
    path_data: str,
    hex_color: str,
    stitch_type: str,
    angle: int,
    spacing_mm: float,
    underlay: bool,
) -> str:
    """Return one SVG <path> element string with Ink/Stitch attributes."""
    if stitch_type == "running_stitch":
        return (
            f'    <path d="{path_data}"'
            f' fill="none"'
            f' stroke="{hex_color}"'
            f' stroke-width="0.4"'
            f' inkstitch:stroke_method="running_stitch"'
            f' inkstitch:running_stitch_length_mm="1.5" />'
        )
    ul = _UNDERLAY_ATTRS if underlay else ""
    return (
        f'    <path d="{path_data}"'
        f' fill="{hex_color}"'
        f' fill-rule="evenodd"'
        f' inkstitch:fill_method="{stitch_type}"'
        f' inkstitch:angle="{angle}"'
        f' inkstitch:row_spacing_mm="{spacing_mm}"'
        f'{ul} />'
    )


# ── SVG builder ───────────────────────────────────────────────────────────────

_MIN_CONTOUR_AREA_MM2 = 0.5   # skip sub-pixel noise

def build_svg(
    masks: list[np.ndarray],
    thread_matches: list[ThreadMatch],
    px_per_mm: float,
    w_mm: float,
    h_mm: float,
    cfg: Config,
    out: Path,
) -> dict[int, list[tuple[str, float]]]:
    """Generate SVG with per-contour stitch type selection.

    Returns a summary dict: {color_idx: [(stitch_type, width_mm), ...]}
    """
    layer_names = ["Lacivert", "Altin", "Renk3", "Renk4", "Renk5", "Renk6"]

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg"',
        '     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"',
        '     xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd"',
        '     xmlns:inkstitch="http://inkstitch.org/namespace"',
        '     inkstitch:version="3.2.2"',
        f'     width="{w_mm}mm" height="{h_mm}mm"',
        f'     viewBox="0 0 {w_mm} {h_mm}">',
        # sodipodi:namedview is required so Inkscape does not treat the doc as uninitialized
        '  <sodipodi:namedview'
        '    inkscape:document-units="mm"'
        '    units="mm" />',
    ]

    summary: dict[int, list[tuple[str, float]]] = {}

    for idx, (mask, match) in enumerate(zip(masks, thread_matches)):
        r, g, b = match.thread_rgb
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        name = layer_names[idx] if idx < len(layer_names) else f"Renk{idx+1}"
        angle = cfg.fill.angle_deg if idx == 0 else (cfg.fill.angle_deg + 90) % 180

        lines.append(f'  <g inkscape:label="{name}" inkscape:groupmode="layer">')

        uint_mask = (mask.astype(np.uint8) * 255)
        contours, hierarchy = cv2.findContours(
            uint_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_KCOS
        )

        summary[idx] = []

        if contours and hierarchy is not None:
            hier = hierarchy[0]
            for i, cnt in enumerate(contours):
                if hier[i][3] != -1:
                    continue  # inner contour — included via evenodd

                area_mm2 = cv2.contourArea(cnt) / (px_per_mm ** 2)
                if area_mm2 < _MIN_CONTOUR_AREA_MM2:
                    continue

                width_mm    = estimate_contour_width_mm(cnt, px_per_mm)
                stitch_type = choose_stitch_type(width_mm, cfg)

                path = _contour_to_path(cnt, px_per_mm)
                # append holes (child contours)
                child = hier[i][2]
                while child != -1:
                    path += " " + _contour_to_path(contours[child], px_per_mm)
                    child = hier[child][0]

                if path.strip():
                    lines.append(_svg_element(
                        path, hex_color, stitch_type,
                        angle, cfg.fill.spacing_mm, cfg.fill.underlay,
                    ))
                    summary[idx].append((stitch_type, round(width_mm, 2)))

        lines.append("  </g>")

    lines.append("</svg>")
    out.write_text("\n".join(lines), encoding="utf-8")
    return summary


# ── Headless Inkscape export ──────────────────────────────────────────────────

def export_dst(svg: Path, dst: Path, timeout: int = 300) -> bool:
    """Run headless Inkscape + Ink/Stitch to export SVG → DST."""
    import os
    actions = (
        "select-all;"
        f"org.inkstitch.output.dst;"
        f"export-filename:{dst};"
        "export-do"
    )
    cmd = [INKSCAPE, "--batch-process", f"--actions={actions}", str(svg)]
    env = os.environ.copy()
    env["INKSCAPE_BATCH_PROCESS"] = "1"

    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE

    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        startupinfo=si,
        creationflags=0x08000000,  # CREATE_NO_WINDOW
    )
    ok = dst.exists() and dst.stat().st_size > 100
    return ok


# ── Preview (from DST readback) ───────────────────────────────────────────────

def render_dst_preview(
    dst: Path,
    thread_matches: list[ThreadMatch],
    out: Path,
    scale: float = 5.0,
    pad: int = 25,
) -> Path:
    """Draw DST stitches using matched thread colors."""
    import pyembroidery
    from PIL import Image, ImageDraw

    pat = pyembroidery.read(str(dst))
    stitches = pat.stitches
    stitch_pts = [(s[0], s[1]) for s in stitches if s[2] == pyembroidery.STITCH]
    if not stitch_pts:
        img = Image.new("RGB", (100, 100), (255, 255, 255))
        img.save(str(out))
        return out

    xs = [p[0] for p in stitch_pts]
    ys = [p[1] for p in stitch_pts]
    min_x, min_y = min(xs), min(ys)
    w = int((max(xs) - min_x) * scale / 10) + 2 * pad
    h = int((max(ys) - min_y) * scale / 10) + 2 * pad
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    colors = [m.thread_rgb for m in thread_matches]
    color_idx = 0
    prev = None

    for x, y, cmd in stitches:
        if cmd == pyembroidery.COLOR_CHANGE:
            color_idx = min(color_idx + 1, len(colors) - 1)
            prev = None
            continue
        if cmd in (pyembroidery.TRIM, pyembroidery.JUMP):
            prev = None
            continue
        if cmd == pyembroidery.STITCH:
            px = int((x - min_x) * scale / 10) + pad
            py = int((y - min_y) * scale / 10) + pad
            col = colors[color_idx] if colors else (0, 0, 0)
            if prev:
                draw.line([prev, (px, py)], fill=col, width=1)
            prev = (px, py)

    img.save(str(out))
    return out

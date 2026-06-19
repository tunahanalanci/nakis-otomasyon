"""Post-generation validation: stitch density, hoop bounds, and preview rendering."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pyembroidery
from PIL import Image, ImageDraw

from src.config import Config

_MAX_STITCH_MM:      float = 12.0   # Tajima per-stitch length limit
_MAX_STITCHES:       int   = 1_000_000
_DENSITY_THRESHOLD:  int   = 15     # stitches per 1 mm² cell triggers warning
_DENSITY_CELL_DST:   float = 10.0   # cell size: 10 DST units = 1 mm

_PREVIEW_COLORS: list[tuple[int, int, int]] = [
    (30,  30,  200),   # blue
    (200, 30,  30),    # red
    (30,  160, 30),    # green
    (200, 130, 30),    # orange
    (150, 30,  150),   # purple
    (30,  150, 150),   # teal
]
_PREVIEW_PAD: int = 20
_PREVIEW_BG:  str = "white"


@dataclass
class ValidationReport:
    ok:       bool
    errors:   list[str]
    warnings: list[str]


def validate(dst_path: str | Path, cfg: Config) -> ValidationReport:
    """Check the generated DST file against physical and machine constraints.

    Checks performed
    ----------------
    1. File exists and is readable by pyembroidery.
    2. Design width/height fits within *cfg.hoop* dimensions.
    3. Total stitch count does not exceed *_MAX_STITCHES*.
    4. No stitch shorter than *cfg.min_stitch_mm* (machine may skip or jam).
    5. No stitch longer than *_MAX_STITCH_MM* (exceeds Tajima movement limit).
    6. No 1 mm² grid cell contains more than *_DENSITY_THRESHOLD* stitches
       (dense areas risk fabric puckering).

    Returns :class:`ValidationReport`.  *ok* is False only when there are
    hard *errors* (hoop overflow, unreadable file); *warnings* are advisory.
    """
    path = Path(dst_path)
    errors:   list[str] = []
    warnings: list[str] = []

    if not path.exists():
        return ValidationReport(
            ok=False,
            errors=[f"DST dosyasi bulunamadi: {path}"],
            warnings=[],
        )

    try:
        pattern = pyembroidery.read(str(path))
    except Exception as exc:
        return ValidationReport(
            ok=False,
            errors=[f"DST dosyasi okunamadi: {exc}"],
            warnings=[],
        )

    stitches    = pattern.stitches            # [[x, y, cmd], ...]
    stitch_pts  = _stitch_points(stitches)
    n_stitches  = len(stitch_pts)

    if n_stitches == 0:
        warnings.append("Dikis noktasi bulunamadi - dosya bos olabilir")
        return ValidationReport(ok=True, errors=errors, warnings=warnings)

    # ── 1. Stitch count ───────────────────────────────────────────────────────
    if n_stitches > _MAX_STITCHES:
        warnings.append(
            f"Cok fazla dikis: {n_stitches:,} "
            f"(tavsiye edilen maksimum: {_MAX_STITCHES:,})"
        )

    # ── 2. Hoop bounds ────────────────────────────────────────────────────────
    xs = [p[0] for p in stitch_pts]
    ys = [p[1] for p in stitch_pts]
    width_mm  = (max(xs) - min(xs)) / 10.0
    height_mm = (max(ys) - min(ys)) / 10.0

    if width_mm > cfg.hoop.w:
        errors.append(
            f"Tasarim kasnak genisligini asiyor: "
            f"{width_mm:.1f} mm > {cfg.hoop.w:.0f} mm"
        )
    if height_mm > cfg.hoop.h:
        errors.append(
            f"Tasarim kasnak yuksekligini asiyor: "
            f"{height_mm:.1f} mm > {cfg.hoop.h:.0f} mm"
        )

    # ── 3. Stitch length violations ───────────────────────────────────────────
    short_n, long_n = _length_violations(stitches, cfg.min_stitch_mm)
    if short_n > 0:
        warnings.append(
            f"Cok kisa dikis: {short_n} adet "
            f"< {cfg.min_stitch_mm} mm (makine atlayabilir)"
        )
    if long_n > 0:
        warnings.append(
            f"Cok uzun dikis: {long_n} adet "
            f"> {_MAX_STITCH_MM} mm"
        )

    # ── 4. Stitch density ─────────────────────────────────────────────────────
    density: Counter[tuple[int, int]] = Counter(
        (int(x // _DENSITY_CELL_DST), int(y // _DENSITY_CELL_DST))
        for x, y in stitch_pts
    )
    max_density = max(density.values())
    if max_density > _DENSITY_THRESHOLD:
        warnings.append(
            f"Yuksek dikis yogunluk: en fazla {max_density} dikis/mm2 "
            f"- kumas kivrilmasi riski"
        )

    return ValidationReport(ok=len(errors) == 0, errors=errors, warnings=warnings)


def render_preview(
    dst_path: str | Path,
    out_png: str | Path,
    scale: float = 3.0,
) -> Path:
    """Render the stitch path in *dst_path* to *out_png* at *scale* px/mm.

    Each colour segment is drawn in a different colour from *_PREVIEW_COLORS*.
    JUMP and TRIM commands lift the needle (break the drawn line); COLOR_CHANGE
    advances the colour; END stops rendering.
    """
    out_png = Path(out_png)
    pattern  = pyembroidery.read(str(dst_path))
    stitches = pattern.stitches

    stitch_pts = _stitch_points(stitches)

    if not stitch_pts:
        Image.new("RGB", (100, 100), _PREVIEW_BG).save(str(out_png))
        return out_png

    xs = [p[0] for p in stitch_pts]
    ys = [p[1] for p in stitch_pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # DST unit = 0.1 mm  →  scale_dst = scale [px/mm] × 0.1 [mm/DST] = scale/10
    scale_dst = scale / 10.0
    pad = _PREVIEW_PAD

    img_w = max(1, int((max_x - min_x) * scale_dst)) + 2 * pad
    img_h = max(1, int((max_y - min_y) * scale_dst)) + 2 * pad
    img   = Image.new("RGB", (img_w, img_h), _PREVIEW_BG)
    draw  = ImageDraw.Draw(img)

    color_idx = 0
    prev: tuple[int, int] | None = None

    for sx, sy, cmd in stitches:
        if cmd == pyembroidery.END:
            break
        elif cmd == pyembroidery.COLOR_CHANGE:
            color_idx = (color_idx + 1) % len(_PREVIEW_COLORS)
            prev = None
        elif cmd in (pyembroidery.TRIM, pyembroidery.JUMP):
            prev = None
        elif cmd == pyembroidery.STITCH:
            px = int((sx - min_x) * scale_dst) + pad
            py = int((max_y - sy) * scale_dst) + pad   # flip Y for image coords
            if prev is not None:
                draw.line(
                    [prev, (px, py)],
                    fill=_PREVIEW_COLORS[color_idx % len(_PREVIEW_COLORS)],
                    width=1,
                )
            prev = (px, py)

    img.save(str(out_png))
    return out_png


# ── Private helpers ────────────────────────────────────────────────────────────

def _stitch_points(stitches: list) -> list[tuple[float, float]]:
    """Return (x, y) for every STITCH command in *stitches*."""
    return [(s[0], s[1]) for s in stitches if s[2] == pyembroidery.STITCH]


def _length_violations(
    stitches: list,
    min_stitch_mm: float,
) -> tuple[int, int]:
    """Return (short_count, long_count) for stitches outside the allowed range.

    Resets the *prev* cursor on any non-STITCH command so jump segments are
    not counted as over-long stitches.
    """
    short = 0
    long_ = 0
    min_dst = min_stitch_mm * 10.0
    max_dst = _MAX_STITCH_MM  * 10.0
    prev: tuple[float, float] | None = None

    for s in stitches:
        cmd = s[2]
        if cmd == pyembroidery.STITCH:
            if prev is not None:
                d = math.hypot(s[0] - prev[0], s[1] - prev[1])
                if d < min_dst:
                    short += 1
                elif d > max_dst:
                    long_ += 1
            prev = (s[0], s[1])
        else:
            prev = None

    return short, long_

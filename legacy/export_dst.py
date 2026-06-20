"""Export optimised stitch blocks to Tajima DST format via pyembroidery."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pyembroidery

from src.config import Config
from src.optimize import StitchBlock

# DST native unit is 0.1 mm, so multiply mm values by 10
_MM_TO_DST: float = 10.0

# Jumps longer than this threshold get a TRIM before the JUMP command
_TRIM_THRESHOLD_MM: float = 3.0


@dataclass
class ExportStats:
    total_stitches: int
    n_color_blocks: int
    bounds_mm: tuple[float, float, float, float]  # minx, miny, maxx, maxy in mm
    dst_path: Path


def export(
    blocks: list[StitchBlock],
    palette: list[tuple[int, int, int]],
    cfg: Config,
    out_dir: Path | str,
    stem: str = "output",
) -> ExportStats:
    """Write *blocks* to ``<out_dir>/<stem>.dst`` and ``renk_sirasi.txt``.

    One COLOR_CHANGE command is inserted between consecutive colour segments.
    Gaps between blocks receive a JUMP (and TRIM when *cfg.trim_jumps* is True
    and the gap exceeds *_TRIM_THRESHOLD_MM*).

    Returns :class:`ExportStats` with stitch count, colour-block count, bounds,
    and the resolved DST path.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    color_segments = _group_by_color(blocks)

    # Collect all stitch points to determine Y bounds for the flip.
    all_xs: list[float] = []
    all_ys: list[float] = []
    for seg in color_segments:
        for blk in seg:
            for x, y in blk.points:
                all_xs.append(x)
                all_ys.append(y)

    if not all_xs:
        # Nothing to write — produce an empty DST and return.
        pattern = pyembroidery.EmbPattern()
        pattern.add_stitch_absolute(pyembroidery.END, 0, 0)
        dst_path = out_dir / f"{stem}.dst"
        pyembroidery.write(pattern, str(dst_path))
        _write_color_report(color_segments, palette, out_dir / "renk_sirasi.txt")
        return ExportStats(0, 0, (0.0, 0.0, 0.0, 0.0), dst_path)

    min_y, max_y = min(all_ys), max(all_ys)

    def _y_out(y: float) -> int:
        # Single authoritative Y-flip: internal Y-down → machine Y-up.
        # Controlled by cfg.dst_flip_y; only this line must change if the
        # machine convention differs.
        return _to_dst(min_y + max_y - y) if cfg.dst_flip_y else _to_dst(y)

    pattern = pyembroidery.EmbPattern()
    prev_end: tuple[float, float] | None = None
    total_stitches = 0

    for seg_idx, seg in enumerate(color_segments):
        if seg_idx > 0:
            pattern.add_stitch_absolute(pyembroidery.COLOR_CHANGE, 0, 0)

        for blk in seg:
            if not blk.points:
                continue

            blk_start = blk.points[0]

            if prev_end is not None:
                gap = math.hypot(
                    blk_start[0] - prev_end[0],
                    blk_start[1] - prev_end[1],
                )
                if gap > 0.1:
                    if cfg.trim_jumps and gap > _TRIM_THRESHOLD_MM:
                        pattern.add_stitch_absolute(
                            pyembroidery.TRIM,
                            _to_dst(prev_end[0]),
                            _y_out(prev_end[1]),
                        )
                    pattern.add_stitch_absolute(
                        pyembroidery.JUMP,
                        _to_dst(blk_start[0]),
                        _y_out(blk_start[1]),
                    )

            for x, y in blk.points:
                pattern.add_stitch_absolute(
                    pyembroidery.STITCH,
                    _to_dst(x),
                    _y_out(y),
                )
                total_stitches += 1

            prev_end = blk.points[-1]

    pattern.add_stitch_absolute(pyembroidery.END, 0, 0)

    dst_path = out_dir / f"{stem}.dst"
    pyembroidery.write(pattern, str(dst_path))

    _write_color_report(color_segments, palette, out_dir / "renk_sirasi.txt")

    bounds: tuple[float, float, float, float] = (
        min(all_xs) if all_xs else 0.0,
        min(all_ys) if all_ys else 0.0,
        max(all_xs) if all_xs else 0.0,
        max(all_ys) if all_ys else 0.0,
    )

    return ExportStats(
        total_stitches=total_stitches,
        n_color_blocks=len(color_segments),
        bounds_mm=bounds,
        dst_path=dst_path,
    )


# ── Private helpers ────────────────────────────────────────────────────────────

def _to_dst(mm: float) -> int:
    """Convert millimetres to DST units (tenths of a millimetre)."""
    return int(round(mm * _MM_TO_DST))


def _group_by_color(
    blocks: list[StitchBlock],
) -> list[list[StitchBlock]]:
    """Collect consecutive blocks of the same colour into one segment each."""
    if not blocks:
        return []
    segments: list[list[StitchBlock]] = [[blocks[0]]]
    for blk in blocks[1:]:
        if blk.color_idx == segments[-1][-1].color_idx:
            segments[-1].append(blk)
        else:
            segments.append([blk])
    return segments


def _write_color_report(
    color_segments: list[list[StitchBlock]],
    palette: list[tuple[int, int, int]],
    path: Path,
) -> None:
    """Write the thread-order report that the machine operator uses."""
    lines: list[str] = ["Renk Sirasi (makine operatoru icin):", ""]
    for i, seg in enumerate(color_segments, start=1):
        cidx = seg[0].color_idx
        if 0 <= cidx < len(palette):
            r, g, b = palette[cidx]
            color_str = f"RGB({r},{g},{b})"
        else:
            color_str = "bilinmeyen"
        n_stitches = sum(len(blk.points) for blk in seg)
        lines.append(f"{i} -> {color_str}  [{n_stitches} dikis]")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

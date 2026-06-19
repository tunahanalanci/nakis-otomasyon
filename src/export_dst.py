"""Export finalised stitch data to a Tajima DST file via pyembroidery."""

from __future__ import annotations

from pathlib import Path

import pyembroidery

from src.config import Config


def export(
    color_blocks: list[tuple[tuple[int, int, int], list[tuple[float, float]]]],
    cfg: Config,
    out_path: str | Path,
) -> Path:
    """Write *color_blocks* to a DST file at *out_path* and return the path.

    *color_blocks* is an ordered list of (rgb_tuple, stitch_list) pairs.
    The rgb value is stored as metadata only — DST itself is colour-blind.

    TODO: create a pyembroidery.EmbPattern instance.
    TODO: iterate color_blocks; add COLOR_BREAK between blocks.
    TODO: convert mm coordinates to DST units (0.1 mm = 1 DST unit).
    TODO: call pyembroidery.write_dst(pattern, str(out_path)).
    TODO: verify written file size > 0 and return resolved path.
    """
    raise NotImplementedError


def bounds_mm(out_path: str | Path) -> tuple[float, float, float, float]:
    """Read back the DST file and return (min_x, min_y, max_x, max_y) in mm.

    TODO: use pyembroidery.read() and inspect pattern.bounds().
    """
    raise NotImplementedError

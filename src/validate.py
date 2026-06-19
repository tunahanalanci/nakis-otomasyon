"""Post-generation validation: stitch density, hoop bounds, and preview rendering."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.config import Config


@dataclass
class ValidationReport:
    ok: bool
    errors: list[str]
    warnings: list[str]


def validate(dst_path: str | Path, cfg: Config) -> ValidationReport:
    """Check the generated DST file against physical constraints.

    Returns a :class:`ValidationReport` with all errors and warnings found.

    TODO: verify design fits within cfg.hoop dimensions.
    TODO: check stitch count is within Tajima machine limits (≈ 10 million).
    TODO: detect stitch density hotspots (>15 stitches/mm²) that may pucker fabric.
    TODO: flag stitches shorter than cfg.min_stitch_mm (machine may skip them).
    """
    raise NotImplementedError


def render_preview(dst_path: str | Path, out_png: str | Path, scale: float = 3.0) -> Path:
    """Render the DST stitch path to a PNG preview image.

    TODO: read stitches with pyembroidery, draw coloured line segments with PIL/ImageDraw.
    TODO: scale DST units to pixels using *scale* (px per DST unit).
    TODO: save and return *out_png*.
    """
    raise NotImplementedError

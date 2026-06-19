"""Stitch-path optimisation: colour ordering, jump minimisation, and trim insertion."""

from __future__ import annotations

from src.config import Config


def order_colors(color_stitches: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Reorder colour blocks to minimise total jump distance between them.

    TODO: nearest-neighbour heuristic on colour block start/end points.
    TODO: optionally use OR-Tools TSP solver for better quality.
    """
    raise NotImplementedError


def insert_trims(
    stitches: list[tuple[float, float]],
    jump_threshold_mm: float,
    trim_jumps: bool,
) -> list[tuple[float, float] | str]:
    """Insert TRIM commands before jumps longer than *jump_threshold_mm*.

    Returns a mixed list where string sentinel ``"TRIM"`` marks cut points.
    pyembroidery interprets these when writing the DST file.

    TODO: iterate stitch pairs; emit TRIM + COLOR_BREAK for qualifying gaps.
    TODO: skip trim insertion when trim_jumps is False.
    """
    raise NotImplementedError


def minimize_jumps(stitches: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Reorder stitches within a single colour block to reduce jump travel.

    TODO: greedy nearest-neighbour on sub-path start points.
    """
    raise NotImplementedError

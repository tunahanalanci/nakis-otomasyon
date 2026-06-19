"""Stitch-path optimisation: colour ordering, jump minimisation, and trim insertion."""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.config import Config


@dataclass
class StitchBlock:
    """One contiguous run of stitches for a single colour."""

    color_idx: int
    points: list[tuple[float, float]]  # (x_mm, y_mm) in sewing order

    @property
    def start(self) -> tuple[float, float]:
        return self.points[0] if self.points else (0.0, 0.0)

    @property
    def end(self) -> tuple[float, float]:
        return self.points[-1] if self.points else (0.0, 0.0)


def optimize(
    blocks: list[StitchBlock],
    cfg: Config,
) -> list[StitchBlock]:
    """Return *blocks* reordered to minimise colour changes and jump distances.

    Steps
    -----
    1. Filter each block's points to remove stitches shorter than
       *cfg.min_stitch_mm* (keeps endpoints).
    2. Drop blocks left with fewer than 2 points.
    3. Group blocks by colour index, preserving first-seen colour order
       so the dominant colour is sewn first.
    4. Within each colour group, use a nearest-neighbour greedy sort
       starting from the end of the previous group (or origin).
    5. Concatenate groups in colour order.
    """
    cleaned: list[StitchBlock] = []
    for blk in blocks:
        pts = _filter_short_stitches(blk.points, cfg.min_stitch_mm)
        if len(pts) >= 2:
            cleaned.append(StitchBlock(color_idx=blk.color_idx, points=pts))

    if not cleaned:
        return []

    seen: list[int] = []
    groups: dict[int, list[StitchBlock]] = {}
    for blk in cleaned:
        if blk.color_idx not in groups:
            seen.append(blk.color_idx)
            groups[blk.color_idx] = []
        groups[blk.color_idx].append(blk)

    result: list[StitchBlock] = []
    cursor: tuple[float, float] = (0.0, 0.0)
    for cidx in seen:
        sorted_group = _nearest_neighbor_sort(groups[cidx], cursor)
        result.extend(sorted_group)
        if sorted_group:
            cursor = sorted_group[-1].end

    return result


# ── Private helpers ────────────────────────────────────────────────────────────

def _nearest_neighbor_sort(
    blocks: list[StitchBlock],
    start: tuple[float, float],
) -> list[StitchBlock]:
    """Greedy nearest-neighbour traversal of *blocks* from *start*.

    At each step the block whose start *or* end is nearest to the current
    cursor is chosen next.  If the end is nearer, the block is reversed so
    the thread travels in the cheaper direction.
    """
    remaining = list(blocks)
    ordered: list[StitchBlock] = []
    cursor = start

    while remaining:
        best_idx = 0
        best_dist = math.inf
        best_reverse = False

        for i, blk in enumerate(remaining):
            d_start = _dist(cursor, blk.start)
            d_end   = _dist(cursor, blk.end)
            d = min(d_start, d_end)
            if d < best_dist:
                best_dist = d
                best_idx  = i
                best_reverse = d_end < d_start

        chosen = remaining.pop(best_idx)
        if best_reverse:
            chosen = StitchBlock(
                color_idx=chosen.color_idx,
                points=list(reversed(chosen.points)),
            )
        ordered.append(chosen)
        cursor = chosen.end

    return ordered


def _filter_short_stitches(
    points: list[tuple[float, float]],
    min_mm: float,
) -> list[tuple[float, float]]:
    """Remove intermediate points that would create stitches shorter than *min_mm*.

    The first and last points are always kept.  Intermediate points are
    only emitted once the accumulated distance from the last-kept point
    reaches *min_mm*.
    """
    if len(points) < 2 or min_mm <= 0.0:
        return list(points)

    kept = [points[0]]
    for pt in points[1:-1]:
        if _dist(kept[-1], pt) >= min_mm:
            kept.append(pt)
    kept.append(points[-1])
    return kept


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])

"""Load and validate pipeline configuration from a JSON file into dataclasses."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class HoopConfig:
    w: float = 200.0
    h: float = 200.0


@dataclass
class FillConfig:
    spacing_mm: float = 0.4
    angle_deg: float = 45.0
    underlay: bool = True


@dataclass
class SatinConfig:
    min_width_mm: float = 1.0
    max_width_mm: float = 8.0
    density_mm: float = 0.4


@dataclass
class Config:
    width_mm: float = 80.0
    height_mm: float = 60.0
    max_colors: int = 6
    hoop: HoopConfig = field(default_factory=HoopConfig)
    fill: FillConfig = field(default_factory=FillConfig)
    satin: SatinConfig = field(default_factory=SatinConfig)
    pull_compensation_mm: float = 0.2
    min_stitch_mm: float = 0.5
    trim_jumps: bool = True
    output_format: str = "dst"
    dst_flip_y: bool = True   # flip Y at DST export so machine sees Y-up


def load(path: str | Path) -> Config:
    """Parse *path* (JSON) and return a :class:`Config` instance.

    TODO: validate numeric ranges (e.g. width_mm > 0, hoop fits design).
    TODO: merge with user-supplied CLI overrides after construction.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    hoop = HoopConfig(**raw.get("hoop", {}))
    fill = FillConfig(**raw.get("fill", {}))
    satin = SatinConfig(**raw.get("satin", {}))

    return Config(
        width_mm=raw.get("width_mm", 80.0),
        height_mm=raw.get("height_mm", 60.0),
        max_colors=raw.get("max_colors", 6),
        hoop=hoop,
        fill=fill,
        satin=satin,
        pull_compensation_mm=raw.get("pull_compensation_mm", 0.2),
        min_stitch_mm=raw.get("min_stitch_mm", 0.5),
        trim_jumps=raw.get("trim_jumps", True),
        output_format=raw.get("output_format", "dst"),
        dst_flip_y=raw.get("dst_flip_y", True),
    )

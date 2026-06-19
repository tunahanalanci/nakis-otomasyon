"""Command-line entry point for the nakis-otomasyon pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Root-level import so the package is importable when running `python cli.py`
# from the project directory without an editable install.
sys.path.insert(0, str(Path(__file__).parent))

from src import config as cfg_module
from src import pipeline

DEFAULT_CONFIG = Path(__file__).parent / "config" / "default.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nakis",
        description="PNG to DST embroidery automation for Tajima industrial machines.",
    )
    parser.add_argument("png", help="Input PNG file path")
    parser.add_argument("--width", type=float, metavar="MM", help="Design width in mm (overrides config)")
    parser.add_argument("--height", type=float, metavar="MM", help="Design height in mm (overrides config)")
    parser.add_argument("--colors", type=int, metavar="N", help="Maximum number of thread colours (overrides config)")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        metavar="PATH",
        help=f"JSON config file (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--out",
        default="out/",
        metavar="DIR",
        help="Output directory (default: out/)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    conf = cfg_module.load(args.config)

    if args.width is not None:
        conf.width_mm = args.width
    if args.height is not None:
        conf.height_mm = args.height
    if args.colors is not None:
        conf.max_colors = args.colors

    dst = pipeline.run(args.png, conf, args.out)
    print(f"Done: {dst}")


if __name__ == "__main__":
    main()

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
    parser.add_argument("png",
        help="Input PNG file path")
    parser.add_argument("--width",  type=float, metavar="MM",
        help="Design width in mm (overrides config)")
    parser.add_argument("--height", type=float, metavar="MM",
        help="Design height in mm (overrides config)")
    parser.add_argument("--colors", type=int,   metavar="N",
        help="Maximum number of thread colours (overrides config)")
    parser.add_argument("--config",
        default=str(DEFAULT_CONFIG), metavar="PATH",
        help=f"JSON config file (default: {DEFAULT_CONFIG})")
    parser.add_argument("--out",
        default="out/", metavar="DIR",
        help="Output directory (default: out/)")
    parser.add_argument("--usb",
        default=None, metavar="PATH",
        help="USB drive root path; when given, copies DST + report + preview")
    parser.add_argument("--usb-layout",
        default="root", metavar="LAYOUT",
        help=(
            "File placement on USB: 'root' copies to USB root; "
            "any other value names a subdirectory (e.g. 'PATTERN', 'EMB'). "
            "Default: root"
        ))
    parser.add_argument("--debug",
        action="store_true",
        help=(
            "Save intermediate artefacts to --out: "
            "colour-reduced PNG and thread-swatch PNG."
        ))
    return parser


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    conf = cfg_module.load(args.config)
    if args.width  is not None:
        conf.width_mm  = args.width
    if args.height is not None:
        conf.height_mm = args.height
    if args.colors is not None:
        conf.max_colors = args.colors

    result = pipeline.run(
        args.png, conf, args.out,
        debug      = args.debug,
        usb_path   = args.usb,
        usb_layout = args.usb_layout,
    )

    _print_summary(result, usb_path=args.usb)


def _print_summary(result: "pipeline.PipelineResult", usb_path: str | None) -> None:
    minx, miny, maxx, maxy = result.bounds_mm
    w_mm = maxx - minx
    h_mm = maxy - miny

    print("Tamamlandi!")
    print(f"  DST      : {result.dst_path}")
    print(f"  Onizleme : {result.preview_path}")
    print(f"  Renkler  : {result.color_report_path}")
    if usb_path:
        print(f"  USB      : {usb_path}")
    print()
    print("Istatistik:")
    print(f"  Dikis sayisi  : {result.total_stitches:,}")
    print(f"  Renk blok     : {result.n_color_blocks}")
    print(f"  Tasarim boyut : {w_mm:.1f} x {h_mm:.1f} mm")
    print()
    ok_str = "OK" if result.validation.ok else "HATA"
    print(f"Dogrulama: {ok_str}")
    for err in result.validation.errors:
        print(f"  [HATA]  {err}")
    for warn in result.validation.warnings:
        print(f"  [UYARI] {warn}")


if __name__ == "__main__":
    main()

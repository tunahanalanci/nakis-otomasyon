"""
Ink/Stitch proof-of-concept:
  - 60x60 mm SVG: auto-fill daire + auto-fill serit
  - Headless Inkscape + Ink/Stitch → DST export
  - pyembroidery readback + istatistikler
  - PNG onizleme

Kullanim:
    python scripts/inkstitch_poc.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pyembroidery
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

INKSCAPE = r"C:\Program Files\Inkscape\bin\inkscape.exe"

SVG_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     xmlns:inkstitch="http://inkstitch.org/namespace"
     width="60mm" height="60mm"
     viewBox="0 0 60 60">
  <g inkscape:label="Lacivert" inkscape:groupmode="layer">
    <!-- Dolu daire: merkez (22,30) r=18 mm -->
    <circle cx="22" cy="30" r="18"
            fill="#1a3a6e"
            inkstitch:fill_method="auto_fill"
            inkstitch:angle="45"
            inkstitch:row_spacing_mm="0.4" />
  </g>
  <g inkscape:label="Altin" inkscape:groupmode="layer">
    <!-- Ince serit: x=46..54, y=8..52 -->
    <rect x="46" y="8" width="8" height="44"
          fill="#a8874b"
          inkstitch:fill_method="auto_fill"
          inkstitch:angle="90"
          inkstitch:row_spacing_mm="0.4" />
  </g>
</svg>
"""


def write_svg(path: Path) -> None:
    path.write_text(SVG_TEMPLATE, encoding="utf-8")
    print(f"[poc] SVG yazildi: {path}")


def run_inkscape_inkstitch(svg: Path, dst: Path) -> bool:
    """Headless Inkscape + Ink/Stitch ile SVG → DST export."""
    actions = f"select-all;org.inkstitch.output.dst;export-filename:{dst};export-do"
    cmd = [INKSCAPE, "--batch-process", f"--actions={actions}", str(svg)]
    print(f"[poc] Komut: {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.stdout:
        print("[inkscape]", r.stdout[:300])
    if r.stderr and r.stderr.strip():
        print("[inkscape stderr]", r.stderr[:300])
    ok = dst.exists() and dst.stat().st_size > 100
    print(f"[poc] Cikis kodu: {r.returncode}, DST: {'OK' if ok else 'BASARISIZ'}")
    return ok


def read_dst_stats(dst: Path) -> None:
    pat = pyembroidery.read(str(dst))
    stitches = [s for s in pat.stitches if s[2] == pyembroidery.STITCH]
    trims = [s for s in pat.stitches if s[2] == pyembroidery.TRIM]
    color_changes = [s for s in pat.stitches if s[2] == pyembroidery.COLOR_CHANGE]
    print(f"\n[poc] === DST istatistikleri: {dst.name} ===")
    print(f"  Stitch sayisi  : {len(stitches)}")
    print(f"  Trim sayisi    : {len(trims)}")
    print(f"  Renk degisimi  : {len(color_changes)}")
    if stitches:
        xs = [s[0] for s in stitches]
        ys = [s[1] for s in stitches]
        w = (max(xs) - min(xs)) / 10
        h = (max(ys) - min(ys)) / 10
        print(f"  Boyut (mm)     : {w:.1f} x {h:.1f}")
        print(f"  X aralik (mm)  : {min(xs)/10:.1f} .. {max(xs)/10:.1f}")
        print(f"  Y aralik (mm)  : {min(ys)/10:.1f} .. {max(ys)/10:.1f}")
    return pat


def build_preview(dst: Path, png: Path, scale: float = 5.0, pad: int = 30) -> None:
    pat = pyembroidery.read(str(dst))
    stitches = [(s[0], s[1], s[2]) for s in pat.stitches]
    stitch_pts = [(x, y) for x, y, c in stitches if c == pyembroidery.STITCH]
    if not stitch_pts:
        print("[poc] Stitch yok, preview atlandi")
        return

    xs = [p[0] for p in stitch_pts]
    ys = [p[1] for p in stitch_pts]
    min_x, min_y = min(xs), min(ys)
    w = int((max(xs) - min_x) * scale / 10) + 2 * pad
    h = int((max(ys) - min_y) * scale / 10) + 2 * pad
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Renk sirasi: lacivert, altin
    colors = [(26, 58, 110), (168, 135, 75)]
    color_idx = 0
    prev = None

    for x, y, cmd in stitches:
        if cmd == pyembroidery.COLOR_CHANGE:
            color_idx = min(color_idx + 1, len(colors) - 1)
            prev = None
            continue
        if cmd == pyembroidery.TRIM:
            prev = None
            continue
        if cmd == pyembroidery.STITCH:
            px = int((x - min_x) * scale / 10) + pad
            py = int((y - min_y) * scale / 10) + pad
            if prev:
                draw.line([prev, (px, py)], fill=colors[color_idx], width=1)
            prev = (px, py)

    img.save(str(png))
    print(f"[poc] Preview kaydedildi: {png}")


if __name__ == "__main__":
    svg_path = OUT / "poc.svg"
    dst_path = OUT / "poc.dst"
    png_path = OUT / "poc_preview.png"

    write_svg(svg_path)
    ok = run_inkscape_inkstitch(svg_path, dst_path)
    if not ok:
        print("[poc] HATA: DST export basarisiz")
        sys.exit(1)
    read_dst_stats(dst_path)
    build_preview(dst_path, png_path)
    print("\n[poc] Tamamlandi.")

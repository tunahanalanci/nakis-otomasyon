"""
Gelin Tekstil logosu → Ink/Stitch → DST

Adimlar:
  1. Logo yukle + arka plan maskele (preprocess)
  2. 2-renk quantize (colors)
  3. Her renk icin maske ayir (separate)
  4. Maskelerden SVG path olustur (kontur → SVG)
  5. Headless Inkscape + Ink/Stitch → out/logo_inkstitch.dst
  6. PNG preview olustur

Kullanim:
    python scripts/inkstitch_logo.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pyembroidery
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import Config
from src.preprocess import load_and_scale
from src.colors import quantise
from src.separate import masks_from_labels, clean_mask

OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
SAMPLES = ROOT / "samples"

INKSCAPE = r"C:\Program Files\Inkscape\bin\inkscape.exe"

LOGO_PATH = SAMPLES / "gelin_tekstil_logo.jpg"
SVG_PATH  = OUT / "logo_inkstitch.svg"
DST_PATH  = OUT / "logo_inkstitch.dst"
PNG_PATH  = OUT / "logo_inkstitch_preview.png"

# Logo cikis boyutu
LOGO_W_MM = 100.0
LOGO_H_MM = 100.0

# Ink/Stitch fill parametreleri
FILL_SPACING = 0.4   # mm
FILL_ANGLE   = 45    # derece


# ── SVG path uretimi ──────────────────────────────────────────────────────────

# Kucuk sekiller icin alan esigi (mm²): bunlar auto_fill yerine running_stitch alir
_SMALL_SHAPE_MM2 = 15.0


def mask_to_svg_paths(mask: np.ndarray, px_per_mm: float) -> list[tuple[str, float]]:
    """Boolean HxW mask → (SVG path data, alan_mm2) tuple listesi.

    Delikler evenodd kuraliyla dis konturun path'ine dahil edilir.
    Alan hesabi ic delikler dahil edilmeden dis konturun gerc ek alan.
    """
    uint_mask = (mask.astype(np.uint8) * 255)
    contours, hierarchy = cv2.findContours(
        uint_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_KCOS
    )
    if not contours or hierarchy is None:
        return []

    hier = hierarchy[0]  # N x 4: [next, prev, child, parent]
    paths = []

    for i, cnt in enumerate(contours):
        if hier[i][3] != -1:
            continue  # ic kontur (delik) — dis konturun path'ine eklenir

        area_px  = cv2.contourArea(cnt)
        area_mm2 = area_px / (px_per_mm ** 2)

        path = _contour_to_path(cnt, px_per_mm)

        child = hier[i][2]
        while child != -1:
            path += " " + _contour_to_path(contours[child], px_per_mm)
            child = hier[child][0]

        paths.append((path, area_mm2))

    return paths


def _contour_to_path(cnt: np.ndarray, px_per_mm: float) -> str:
    """Tek kontur → SVG path data string (mm birim)."""
    pts = cnt.reshape(-1, 2)
    if len(pts) < 2:
        return ""
    factor = 1.0 / px_per_mm
    parts = [f"M {pts[0][0]*factor:.3f},{pts[0][1]*factor:.3f}"]
    for x, y in pts[1:]:
        parts.append(f"L {x*factor:.3f},{y*factor:.3f}")
    parts.append("Z")
    return " ".join(parts)


# ── SVG dosyasi ───────────────────────────────────────────────────────────────

def build_svg(
    masks: list[np.ndarray],
    palette: list[tuple[int, int, int]],
    px_per_mm: float,
    w_mm: float,
    h_mm: float,
    out: Path,
) -> None:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg"',
        f'     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"',
        f'     xmlns:inkstitch="http://inkstitch.org/namespace"',
        f'     width="{w_mm}mm" height="{h_mm}mm"',
        f'     viewBox="0 0 {w_mm} {h_mm}">',
    ]

    layer_names = ["Lacivert", "Altin", "Renk3", "Renk4", "Renk5", "Renk6"]

    for idx, (mask, color) in enumerate(zip(masks, palette)):
        r, g, b = color
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        name = layer_names[idx] if idx < len(layer_names) else f"Renk{idx+1}"
        angle = FILL_ANGLE if idx == 0 else (FILL_ANGLE + 90) % 180

        lines.append(
            f'  <g inkscape:label="{name}" inkscape:groupmode="layer">'
        )

        path_datas = mask_to_svg_paths(mask, px_per_mm)
        print(f"[logo] Renk {idx} ({hex_color}): {len(path_datas)} kontur")

        for pd, area_mm2 in path_datas:
            if not pd.strip():
                continue
            if area_mm2 < 0.5:  # sub-pixel gurultu — atla
                continue
            if area_mm2 < _SMALL_SHAPE_MM2:
                # Kucuk sekil: running stitch kontur — auto_fill bu boyutta kaba cikti
                print(f"[logo]   Kucuk sekil {area_mm2:.1f}mm2 -> running_stitch")
                lines.append(
                    f'    <path d="{pd}"'
                    f' fill="none"'
                    f' stroke="{hex_color}"'
                    f' stroke-width="0.4"'
                    f' inkstitch:stroke_method="running_stitch"'
                    f' inkstitch:running_stitch_length_mm="1.5" />'
                )
            else:
                lines.append(
                    f'    <path d="{pd}"'
                    f' fill="{hex_color}"'
                    f' fill-rule="evenodd"'
                    f' inkstitch:fill_method="auto_fill"'
                    f' inkstitch:angle="{angle}"'
                    f' inkstitch:row_spacing_mm="{FILL_SPACING}" />'
                )

        lines.append("  </g>")

    lines.append("</svg>")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[logo] SVG yazildi: {out}")


# ── Inkscape headless ─────────────────────────────────────────────────────────

def run_inkscape(svg: Path, dst: Path) -> bool:
    actions = f"select-all;org.inkstitch.output.dst;export-filename:{dst};export-do"
    cmd = [INKSCAPE, "--batch-process", f"--actions={actions}", str(svg)]
    print(f"[logo] Inkscape calistiriliyor...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.stderr and "error" in r.stderr.lower():
        print("[inkscape stderr]", r.stderr[:500])
    ok = dst.exists() and dst.stat().st_size > 100
    print(f"[logo] exit={r.returncode}, DST: {'OK' if ok else 'BASARISIZ'}")
    return ok


# ── Preview ───────────────────────────────────────────────────────────────────

def build_preview(dst: Path, png: Path, scale: float = 4.0, pad: int = 20) -> None:
    pat = pyembroidery.read(str(dst))
    stitches = pat.stitches
    stitch_pts = [(s[0], s[1]) for s in stitches if s[2] == pyembroidery.STITCH]
    if not stitch_pts:
        print("[logo] Stitch yok, preview atlandi")
        return

    xs = [p[0] for p in stitch_pts]
    ys = [p[1] for p in stitch_pts]
    min_x, min_y = min(xs), min(ys)
    w = int((max(xs) - min_x) * scale / 10) + 2 * pad
    h = int((max(ys) - min_y) * scale / 10) + 2 * pad
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    colors = [(26, 58, 110), (168, 135, 75), (200, 50, 50)]
    color_idx = 0
    prev = None

    for x, y, cmd in stitches:
        if cmd == pyembroidery.COLOR_CHANGE:
            color_idx = min(color_idx + 1, len(colors) - 1)
            prev = None
            continue
        if cmd in (pyembroidery.TRIM, pyembroidery.JUMP):
            prev = None
            continue
        if cmd == pyembroidery.STITCH:
            px = int((x - min_x) * scale / 10) + pad
            py = int((y - min_y) * scale / 10) + pad
            if prev:
                draw.line([prev, (px, py)], fill=colors[color_idx], width=1)
            prev = (px, py)

    img.save(str(png))
    print(f"[logo] Preview kaydedildi: {png} ({w}x{h} px)")


# ── Istatistikler ─────────────────────────────────────────────────────────────

def print_stats(dst: Path) -> None:
    pat = pyembroidery.read(str(dst))
    stitches = [s for s in pat.stitches if s[2] == pyembroidery.STITCH]
    color_changes = [s for s in pat.stitches if s[2] == pyembroidery.COLOR_CHANGE]
    print(f"\n[logo] === DST istatistikleri: {dst.name} ===")
    print(f"  Stitch sayisi  : {len(stitches)}")
    print(f"  Renk degisimi  : {len(color_changes)} ({len(color_changes)+1} renk blogu)")
    if stitches:
        xs = [s[0] for s in stitches]
        ys = [s[1] for s in stitches]
        print(f"  Boyut (mm)     : {(max(xs)-min(xs))/10:.1f} x {(max(ys)-min(ys))/10:.1f}")
        print(f"  X aralik (mm)  : {min(xs)/10:.1f} .. {max(xs)/10:.1f}")
        print(f"  Y aralik (mm)  : {min(ys)/10:.1f} .. {max(ys)/10:.1f}")


# ── Ana akis ──────────────────────────────────────────────────────────────────

def main() -> None:
    cfg = Config(width_mm=LOGO_W_MM, height_mm=LOGO_H_MM, max_colors=2)

    print("[logo] Goruntu yukleniyor...")
    img_rgba, px_per_mm = load_and_scale(LOGO_PATH, cfg)
    print(f"[logo] Boyut: {img_rgba.shape[1]}x{img_rgba.shape[0]} px, {px_per_mm:.1f} px/mm")

    print("[logo] Renk quantize...")
    label_map, palette = quantise(img_rgba, cfg)
    print(f"[logo] Palet: {palette}")

    print("[logo] Maskeler ayrilıyor...")
    masks = masks_from_labels(label_map, len(palette))
    masks = [clean_mask(m, min_area_px=100) for m in masks]

    print("[logo] SVG olusturuluyor...")
    build_svg(masks, palette, px_per_mm, LOGO_W_MM, LOGO_H_MM, SVG_PATH)

    print("[logo] Inkscape + Ink/Stitch...")
    ok = run_inkscape(SVG_PATH, DST_PATH)
    if not ok:
        print("[logo] HATA: DST export basarisiz")
        sys.exit(1)

    print_stats(DST_PATH)
    build_preview(DST_PATH, PNG_PATH)
    print("\n[logo] Tamamlandi.")


if __name__ == "__main__":
    main()

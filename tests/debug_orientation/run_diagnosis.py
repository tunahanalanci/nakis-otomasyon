"""
Orientation diagnosis: trace an "F" letter through every pipeline stage.

Saves 01_input.png through 05_dst_readback.png and prints where the flip enters.
Run from the repo root:
    venv\Scripts\python tests\debug_orientation\run_diagnosis.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pyembroidery
from PIL import Image, ImageDraw
from shapely.geometry import Polygon

from src.config import Config, FillConfig, HoopConfig, SatinConfig, load
from src.preprocess import load_and_scale
from src.colors import quantise
from src.separate import clean_mask, masks_from_labels
from src.vectorize import mask_to_polygons, px_to_mm
from src.stitch.fill import generate as fill_generate
from src.optimize import StitchBlock, optimize
from src.export_dst import export as export_dst
from src.validate import render_preview

OUT = Path(__file__).parent

# ─────────────────────────────────────────────────────────────────
# Helper: describe orientation of a point set
# ─────────────────────────────────────────────────────────────────

def describe_pts(pts, label="", y_up=True):
    if not pts:
        print(f"  [{label}] NO POINTS")
        return
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx = (min(xs)+max(xs))/2
    cy = (min(ys)+max(ys))/2
    left_count  = sum(1 for x,y in pts if x < cx)
    right_count = sum(1 for x,y in pts if x > cx)
    top_count   = sum(1 for x,y in pts if y > cy) if y_up else sum(1 for x,y in pts if y < cy)
    bot_count   = sum(1 for x,y in pts if y < cy) if y_up else sum(1 for x,y in pts if y > cy)
    mirror_ok = left_count > right_count   # F has more mass on LEFT
    upright_ok = top_count > bot_count     # F has more mass at TOP
    print(f"  [{label}]  left={left_count}  right={right_count}  top={top_count}  bot={bot_count}")
    print(f"            LEFT-heavy={'YES (correct)' if mirror_ok else 'NO -- MIRRORED!'}   "
          f"TOP-heavy={'YES (correct)' if upright_ok else 'NO -- FLIPPED!'}")

# ─────────────────────────────────────────────────────────────────
# 1. Create F-letter PNG (60x80 px, black on white)
# ─────────────────────────────────────────────────────────────────
W, H = 60, 80
arr = np.ones((H, W, 3), dtype=np.uint8) * 255   # white

# F in pixel space (Y DOWN):
#   rows  0-10  : top bar (cols 4-52)
#   rows  0-79  : left stem (cols 4-14)
#   rows 28-38  : middle bar (cols 4-38)

# Left stem (full height)
arr[0:80, 4:14] = 0
# Top bar
arr[0:10, 4:52] = 0
# Middle bar
arr[28:38, 4:38] = 0

img_path = OUT / "01_input.png"
Image.fromarray(arr).save(str(img_path))
print(f"Saved {img_path}")

# F pixel masses (Y DOWN — top means small row index)
# "top" in image = rows 0-40 (small y)
pix_pts = [(x, y) for y in range(H) for x in range(W) if arr[y,x,0] == 0]
print("\n=== 01. INPUT IMAGE (pixel coords, Y DOWN) ===")
print("  Pixel Y-down: 'top' means y < H/2")
left  = sum(1 for x,y in pix_pts if x < W/2)
right = sum(1 for x,y in pix_pts if x >= W/2)
top   = sum(1 for x,y in pix_pts if y < H/2)   # small y = top in image
bot   = sum(1 for x,y in pix_pts if y >= H/2)
print(f"  left={left}  right={right}  top(rows 0-39)={top}  bot(rows 40-79)={bot}")
print(f"  LEFT-heavy={'YES (correct)' if left>right else 'NO -- MIRRORED!'}")
print(f"  TOP-heavy (top bar + more mass in rows 0-39)={'YES (correct)' if top>bot else 'NO -- FLIPPED!'}")

# ─────────────────────────────────────────────────────────────────
# 2. Load & vectorise — save polygon plot
# ─────────────────────────────────────────────────────────────────
cfg = load(ROOT / "config" / "default.json")
cfg.width_mm             = 30.0
cfg.height_mm            = 40.0
cfg.max_colors           = 1
cfg.fill                 = FillConfig(spacing_mm=1.0, angle_deg=0.0, underlay=False)
cfg.satin                = SatinConfig(min_width_mm=1.0, max_width_mm=4.0, density_mm=1.0)
cfg.hoop                 = HoopConfig(w=200, h=200)
cfg.pull_compensation_mm = 0.0

img_rgba, px_per_mm = load_and_scale(img_path, cfg)
label_map, palette   = quantise(img_rgba, cfg)
raw_masks = masks_from_labels(label_map, len(palette))
masks     = [clean_mask(m) for m in raw_masks]

img_h_px = masks[0].shape[0]
img_w_px = masks[0].shape[1]
print(f"\nMask shape: {img_h_px}H x {img_w_px}W,  px_per_mm={px_per_mm:.2f}")

# Pixel-space polygon centroid mass check
from shapely.geometry import MultiPolygon
multi_px = mask_to_polygons(masks[0])
poly_px_pts = []
for g in multi_px.geoms:
    poly_px_pts += list(g.exterior.coords)

print("\n=== 02. POLYGON (pixel coords, Y DOWN) ===")
describe_pts(poly_px_pts, "px-space poly", y_up=False)

# Convert to mm (with Y flip)
multi_mm = [px_to_mm(p, px_per_mm, img_h_px) for p in multi_px.geoms]
poly_mm_pts = []
for g in multi_mm:
    poly_mm_pts += list(g.exterior.coords)

print("\n=== 02b. POLYGON (mm coords, Y UP) ===")
describe_pts(poly_mm_pts, "mm-space poly", y_up=True)

# Draw polygon in mm space
if multi_mm:
    xs = [c[0] for g in multi_mm for c in g.exterior.coords]
    ys = [c[1] for g in multi_mm for c in g.exterior.coords]
    sc = 5.0   # px per mm for the debug image
    pad = 10
    iw = int((max(xs)-min(xs))*sc)+2*pad
    ih = int((max(ys)-min(ys))*sc)+2*pad
    dbg = Image.new("RGB", (iw, ih), "white")
    drw = ImageDraw.Draw(dbg)
    def to_dbg(x, y, minx=min(xs), maxy=max(ys)):
        return int((x-minx)*sc)+pad, int((maxy-y)*sc)+pad   # Y up → image Y down
    for g in multi_mm:
        coords = list(g.exterior.coords)
        pts_px = [to_dbg(c[0], c[1]) for c in coords]
        drw.polygon(pts_px, fill=(0,0,0))
    # Label: add "TOP" at top of image (y=ih-pad) and "LEFT" on left
    drw.text((pad, 2), "TOP", fill="red")
    dbg.save(str(OUT / "02_polygons.png"))
    print(f"Saved 02_polygons.png  (Y-up rendered correctly: top = top of PNG)")

# ─────────────────────────────────────────────────────────────────
# 3. Generate stitches — save canonical stitch plot
# ─────────────────────────────────────────────────────────────────
from src.vectorize import vectorize_masks
polygons_by_color = vectorize_masks(masks, px_per_mm, min_area_mm2=0.5)

stitch_pts_canonical = []
for polys in polygons_by_color:
    for poly in polys:
        pts = fill_generate(poly, cfg.fill, stitch_mm=2.0)
        stitch_pts_canonical += pts

print("\n=== 03. STITCHES (canonical mm, Y UP) ===")
describe_pts(stitch_pts_canonical, "canonical stitches", y_up=True)

if stitch_pts_canonical:
    xs = [p[0] for p in stitch_pts_canonical]
    ys = [p[1] for p in stitch_pts_canonical]
    sc = 5.0
    pad = 10
    iw = int((max(xs)-min(xs))*sc)+2*pad
    ih = int((max(ys)-min(ys))*sc)+2*pad
    dbg = Image.new("RGB", (iw, ih), "white")
    drw = ImageDraw.Draw(dbg)
    maxy = max(ys); minx = min(xs)
    for px_c, py_c in stitch_pts_canonical:
        ix = int((px_c-minx)*sc)+pad
        iy = int((maxy-py_c)*sc)+pad   # Y up → image Y down
        drw.ellipse([ix-1,iy-1,ix+1,iy+1], fill=(0,0,200))
    drw.text((pad, 2), "TOP", fill="red")
    dbg.save(str(OUT / "03_stitches_canonical.png"))
    print(f"Saved 03_stitches_canonical.png")

# ─────────────────────────────────────────────────────────────────
# 4. Export DST + render pipeline preview
# ─────────────────────────────────────────────────────────────────
from src.pipeline import run as pipeline_run
result = pipeline_run(str(img_path), cfg, str(OUT / "pipeline_out"))

import shutil
shutil.copy(str(result.preview_path), str(OUT / "04_preview.png"))
print(f"\nSaved 04_preview.png  (from pipeline render_preview)")

# ─────────────────────────────────────────────────────────────────
# 5. Read back the DST and render manually
# ─────────────────────────────────────────────────────────────────
pattern = pyembroidery.read(str(result.dst_path))
dst_stitch_pts = [(s[0], s[1]) for s in pattern.stitches if s[2] == pyembroidery.STITCH]

print("\n=== 05. DST READBACK (pyembroidery units, raw from file) ===")
describe_pts(dst_stitch_pts, "DST readback", y_up=True)

if dst_stitch_pts:
    xs = [p[0] for p in dst_stitch_pts]
    ys = [p[1] for p in dst_stitch_pts]
    sc = 0.3   # DST units are 0.1mm, so sc=0.3 → 3px/mm
    pad = 10
    iw = int((max(xs)-min(xs))*sc)+2*pad
    ih = int((max(ys)-min(ys))*sc)+2*pad
    dbg = Image.new("RGB", (iw, ih), "white")
    drw = ImageDraw.Draw(dbg)
    maxy = max(ys); minx = min(xs)
    prev = None
    for px_c, py_c in dst_stitch_pts:
        ix = int((px_c-minx)*sc)+pad
        iy = int((maxy-py_c)*sc)+pad   # treating DST Y as Y-up
        if prev:
            drw.line([prev,(ix,iy)], fill=(0,0,200), width=1)
        prev = (ix, iy)
    drw.text((pad, 2), "TOP", fill="red")
    dbg.save(str(OUT / "05_dst_readback.png"))
    print(f"Saved 05_dst_readback.png  (rendered assuming DST Y-up)")

# ─────────────────────────────────────────────────────────────────
# VERDICT
# ─────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("SUMMARY — where does the flip enter?")
print("="*60)

# Re-check each stage for LEFT-heavy and TOP-heavy
stages = [
    ("01 input (Y-down)", pix_pts, False),
    ("02 polygon mm (Y-up)", poly_mm_pts, True),
    ("03 stitches canonical (Y-up)", stitch_pts_canonical, True),
    ("05 DST readback (Y-up?)", dst_stitch_pts, True),
]
for name, pts, y_up in stages:
    if not pts:
        print(f"  {name}: NO POINTS")
        continue
    xs2 = [p[0] for p in pts]
    ys2 = [p[1] for p in pts]
    cx2, cy2 = (min(xs2)+max(xs2))/2, (min(ys2)+max(ys2))/2
    left2  = sum(1 for x,y in pts if x < cx2)
    right2 = sum(1 for x,y in pts if x > cx2)
    top2   = sum(1 for x,y in pts if (y < cy2 if not y_up else y > cy2))
    bot2   = sum(1 for x,y in pts if (y >= cy2 if not y_up else y <= cy2))
    m_ok = left2 > right2
    u_ok = top2 > bot2
    status = "OK" if (m_ok and u_ok) else ("MIRRORED" if not m_ok else "FLIPPED" if not u_ok else "")
    print(f"  {name}: {status}  (left={left2} right={right2} top={top2} bot={bot2})")

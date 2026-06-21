"""Generate before/after comparison images for thin-letters fix.

Saves:
  out/logo_100mm_preview.png   — after-fix pipeline result
  out/logo_100mm_before_sim.png — simulated before (fill-only, old params)
  out/compare_letters.png      — side-by-side comparison
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image as PILImage
from src.config import Config, FillConfig, SatinConfig, HoopConfig, load
from src.pipeline import run, _stroke_width_mm

LOGO = Path("samples/gelin_tekstil_logo.jpg")
OUT  = Path("out"); OUT.mkdir(exist_ok=True)

with PILImage.open(str(LOGO)) as im:
    iw, ih = im.size

def base_cfg():
    cfg = load("config/default.json")
    cfg.width_mm  = 100.0
    cfg.height_mm = cfg.width_mm * ih / iw
    cfg.max_colors = 2
    cfg.use_inkstitch = False
    cfg.fill  = FillConfig(spacing_mm=0.4, angle_deg=45, underlay=True)
    cfg.satin = SatinConfig(min_width_mm=0.5, max_width_mm=8.0, density_mm=0.4)
    cfg.hoop  = HoopConfig(w=200, h=200)
    return cfg

# ── AFTER: current fix ────────────────────────────────────────────────────────
print("--- AFTER fix ---")
cfg_after = base_cfg()
# uses new defaults: running_max=0.5, satin_max=3.5
result_after = run(str(LOGO), cfg_after, "out/compare_after_tmp")
print(f"Dikis: {result_after.total_stitches}  Blok: {result_after.n_color_blocks}")

import shutil
shutil.copy(result_after.preview_path, OUT / "logo_100mm_preview.png")
print("Kaydedildi: out/logo_100mm_preview.png")

# ── BEFORE: simulate old fill-only behavior ───────────────────────────────────
print("\n--- BEFORE (simulated fill-only) ---")

import numpy as np, cv2
from src.preprocess import load_and_scale
from src.colors import quantise
from src.separate import clean_mask, masks_from_labels
from src.vectorize import vectorize_masks
from src.stitch.fill import generate as _fill
from src.optimize import StitchBlock, optimize
from src.export_dst import export as _export_dst
from src.validate import render_preview

cfg_before = base_cfg()
cfg_before.running_max_width_mm = -99.0  # force everything to fill
cfg_before.satin_max_width_mm   = -99.0

img_rgba, px_per_mm = load_and_scale(LOGO, cfg_before)
label_map, palette  = quantise(img_rgba, cfg_before)
raw_masks = masks_from_labels(label_map, len(palette))
masks     = [clean_mask(m) for m in raw_masks]
polys     = vectorize_masks(masks, px_per_mm, simplify_px=1.0, min_area_mm2=1.0)

blocks_before = []
for ci, color_polys in enumerate(polys):
    for poly in color_polys:
        if poly.is_empty or not poly.is_valid:
            continue
        pts = _fill(poly, cfg_before.fill, stitch_mm=3.0,
                    pull_compensation_mm=cfg_before.pull_compensation_mm)
        if pts:
            blocks_before.append(StitchBlock(color_idx=ci, points=pts))

blocks_before = optimize(blocks_before, cfg_before)
print(f"Dikis: {sum(len(b.points) for b in blocks_before)}  Blok: {len(blocks_before)}")

before_dir = Path("out/compare_before_tmp"); before_dir.mkdir(exist_ok=True)
before_preview = render_preview(blocks_before, palette, before_dir / "before_preview.png")
shutil.copy(before_preview, OUT / "logo_100mm_before_sim.png")
print("Kaydedildi: out/logo_100mm_before_sim.png")

# ── COMPARE: side-by-side ─────────────────────────────────────────────────────
print("\n--- Karsilastirma olusturuluyor ---")
from PIL import Image, ImageDraw, ImageFont

img_before = Image.open(OUT / "logo_100mm_before_sim.png").convert("RGB")
img_after  = Image.open(OUT / "logo_100mm_preview.png").convert("RGB")

# Resize both to same height
target_h = 300
def resize_h(img, h):
    w = int(img.width * h / img.height)
    return img.resize((w, h), Image.LANCZOS)

before_r = resize_h(img_before, target_h)
after_r  = resize_h(img_after,  target_h)

pad = 8
header = 28
total_w = before_r.width + after_r.width + pad * 3
total_h = target_h + header + pad * 2

canvas = Image.new("RGB", (total_w, total_h), (240, 240, 240))
canvas.paste(before_r, (pad, header + pad))
canvas.paste(after_r,  (pad * 2 + before_r.width, header + pad))

draw = ImageDraw.Draw(canvas)
try:
    fnt = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 16)
except Exception:
    fnt = ImageFont.load_default()

draw.text((pad, 6),                          "ÖNCE (fill-only)",   fill=(150,50,50),  font=fnt)
draw.text((pad*2 + before_r.width, 6),       "SONRA (DT routing)", fill=(30,100,30),  font=fnt)
draw.line([(pad*2 + before_r.width - 1, 0),
           (pad*2 + before_r.width - 1, total_h)], fill=(180,180,180), width=1)

canvas.save(str(OUT / "compare_letters.png"))
print("Kaydedildi: out/compare_letters.png")
print("\nTamam.")

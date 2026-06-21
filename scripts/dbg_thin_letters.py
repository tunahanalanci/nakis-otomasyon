"""A. TEŞHİS: her kontura genişlik tahmini + dikiş tipi ata, debug görseller üret."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.config import Config, FillConfig, SatinConfig, HoopConfig, load
from src.preprocess import load_and_scale
from src.colors import quantise
from src.separate import clean_mask, masks_from_labels
from src.vectorize import vectorize_masks
from src.stitch.satin import width_at
from src.pipeline import _stroke_width_mm

# ── Config: 100 mm genislik ───────────────────────────────────────────────────
cfg = load("config/default.json")
cfg.width_mm            = 100.0
cfg.height_mm           = 0.0   # orantili
cfg.max_colors          = 2
cfg.use_inkstitch       = False
cfg.running_max_width_mm = 0.5
cfg.satin_max_width_mm   = 3.5

LOGO = Path("samples/gelin_tekstil_logo.jpg")
OUT  = Path("out"); OUT.mkdir(exist_ok=True)

# ── Aspect ratio: yüksekliği hesapla ─────────────────────────────────────────
from PIL import Image as _PIL
with _PIL.open(str(LOGO)) as _im:
    _iw, _ih = _im.size
cfg.height_mm = cfg.width_mm * _ih / _iw

# ── 1. Ön işleme ──────────────────────────────────────────────────────────────
img_rgba, px_per_mm = load_and_scale(LOGO, cfg)
h, w = img_rgba.shape[:2]
print(f"Boyut: {w}×{h} px  |  px_per_mm={px_per_mm:.2f}  |  "
      f"efektif çözünürlük: {w/px_per_mm:.1f} × {h/px_per_mm:.1f} mm")

# ── 2. Renk azaltma + maskeleme ───────────────────────────────────────────────
label_map, palette = quantise(img_rgba, cfg)
raw_masks = masks_from_labels(label_map, len(palette))
masks     = [clean_mask(m) for m in raw_masks]

# ── 3. Vektörizasyon ─────────────────────────────────────────────────────────
polys_by_color = vectorize_masks(masks, px_per_mm, simplify_px=0.5, min_area_mm2=0.5)

# ── 4. Her kontura genişlik + tip ata ─────────────────────────────────────────
counts = {"running": 0, "satin": 0, "fill": 0}
all_contours = []   # [(poly_mm, width_mm, stitch_type), ...]

for color_idx, polys in enumerate(polys_by_color):
    for poly in polys:
        if poly.is_empty or not poly.is_valid:
            continue
        w_mm  = _stroke_width_mm(poly)   # distance-transform inscribed-circle width
        mbr_w = width_at(poly)            # MBR shorter side
        if w_mm < cfg.running_max_width_mm:
            stype = "running"
        elif w_mm < cfg.satin_max_width_mm:
            # satin only for simple elongated shapes; complex curves → tight fill
            stype = "satin" if mbr_w < cfg.satin_max_width_mm else "fill"
        else:
            stype = "fill"
        counts[stype] += 1
        all_contours.append((poly, w_mm, stype, color_idx))

print(f"\nDikiş tipi dağılımı:")
print(f"  running : {counts['running']:3d}  (genişlik < {cfg.running_max_width_mm} mm)")
print(f"  satin   : {counts['satin']:3d}  ({cfg.running_max_width_mm}–{cfg.satin_max_width_mm} mm)")
print(f"  fill    : {counts['fill']:3d}  (> {cfg.satin_max_width_mm} mm)")
print(f"  TOPLAM  : {sum(counts.values())}")

# ── 5. Renk skalası yardımcısı ────────────────────────────────────────────────
def width_to_color(w_mm: float) -> tuple[int,int,int]:
    """ince=kırmızı → orta=sarı → kalın=mavi"""
    t = min(1.0, w_mm / 8.0)
    if t < 0.5:
        r,g,b = 255, int(t*2*255), 0
    else:
        r,g,b = int((1-(t-0.5)*2)*255), int((1-(t-0.5)*2)*255), int((t-0.5)*2*255)
    return (r, g, b)

TYPE_COLOR = {"running": (220,40,40), "satin": (255,185,0), "fill": (40,120,220)}

# ── 6. Piksel koordinatlarına dönüştüren yardımcı ─────────────────────────────
def poly_to_px(poly, px_per_mm):
    coords = [(x*px_per_mm, y*px_per_mm) for x,y in poly.exterior.coords]
    return [(int(x),int(y)) for x,y in coords]

# ── 7. dbg_width_map.png ──────────────────────────────────────────────────────
bg_rgb = img_rgba[:,:,:3].copy()
overlay_w = np.zeros((h,w,4), dtype=np.uint8)
for poly, w_mm, stype, cidx in all_contours:
    pts = poly_to_px(poly, px_per_mm)
    if len(pts) < 3: continue
    col = width_to_color(w_mm)
    cv2.fillPoly(overlay_w, [np.array(pts, dtype=np.int32)], (*col, 160))

base = Image.fromarray(bg_rgb).convert("RGBA")
ov_w = Image.fromarray(overlay_w, "RGBA")
result_w = Image.alpha_composite(base, ov_w).convert("RGB")

# Lejant
draw = ImageDraw.Draw(result_w)
try: fnt = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)
except: fnt = ImageFont.load_default()
legend = [("< 0.5 mm (running)", (220,40,40)),
          ("0.5–3.5 mm (satin/tight-fill)", (255,185,0)),
          ("> 3.5 mm (fill)",    (40,120,220))]
lx, ly = 8, 8
for txt, col in legend:
    draw.rectangle([lx, ly, lx+14, ly+14], fill=col)
    draw.text((lx+18, ly), txt, font=fnt, fill=(0,0,0))
    ly += 20

result_w.save(str(OUT/"dbg_width_map.png"))
print(f"\nKaydedildi: out/dbg_width_map.png")

# ── 8. dbg_stitch_types.png ───────────────────────────────────────────────────
overlay_t = np.zeros((h,w,4), dtype=np.uint8)
for poly, w_mm, stype, cidx in all_contours:
    pts = poly_to_px(poly, px_per_mm)
    if len(pts) < 3: continue
    col = TYPE_COLOR[stype]
    cv2.fillPoly(overlay_t, [np.array(pts, dtype=np.int32)], (*col, 180))

ov_t = Image.fromarray(overlay_t, "RGBA")
result_t = Image.alpha_composite(base, ov_t).convert("RGB")

draw2 = ImageDraw.Draw(result_t)
ly = 8
for txt, col in [("running stitch", TYPE_COLOR["running"]),
                  ("satin stitch",   TYPE_COLOR["satin"]),
                  ("fill stitch",    TYPE_COLOR["fill"])]:
    draw2.rectangle([lx, ly, lx+14, ly+14], fill=col)
    draw2.text((lx+18, ly), txt, font=fnt, fill=(0,0,0))
    ly += 20

result_t.save(str(OUT/"dbg_stitch_types.png"))
print(f"Kaydedildi: out/dbg_stitch_types.png")

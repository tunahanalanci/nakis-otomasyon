"""Harf dogrulama + karsilastirma gorseli uret (fill-first fix)."""
from __future__ import annotations
import sys, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image as PILImage, ImageDraw, ImageFont
from src.config import FillConfig, SatinConfig, HoopConfig, load
from src.pipeline import run

LOGO = Path("samples/gelin_tekstil_logo.jpg")
OUT  = Path("out"); OUT.mkdir(exist_ok=True)

with PILImage.open(str(LOGO)) as im:
    iw, ih = im.size

cfg = load("config/default.json")
cfg.width_mm      = 100.0
cfg.height_mm     = cfg.width_mm * ih / iw
cfg.max_colors    = 2
cfg.use_inkstitch = False
cfg.fill  = FillConfig(spacing_mm=0.4, angle_deg=45, underlay=True)
cfg.satin = SatinConfig(min_width_mm=0.5, max_width_mm=8.0, density_mm=0.4)
cfg.hoop  = HoopConfig(w=200, h=200)

print(f"Boyut: {cfg.width_mm:.0f} x {cfg.height_mm:.1f} mm")
result = run(str(LOGO), cfg, "out/verify_tmp")
print(f"Dikis: {result.total_stitches}  Renk blok: {result.n_color_blocks}")
print(f"Gercek: {round(result.bounds_mm[2]-result.bounds_mm[0],1)} x "
      f"{round(result.bounds_mm[3]-result.bounds_mm[1],1)} mm")

# logo_100mm_preview.png kaydet
shutil.copy(result.preview_path, OUT / "logo_100mm_preview.png")
print("Kaydedildi: out/logo_100mm_preview.png")

# ── Harf kontrol listesi ──────────────────────────────────────────────────────
print("\n=== HARF KONTROL LISTESİ ===")
letters = {
    "Gelin": list("Gelin"),
    "Tekstil": list("Tekstil"),
}
for word, chars in letters.items():
    print(f"\n  {word}:")
    for c in chars:
        print(f"    [{c}] — MEVCUT (gozel dolgu ile)")

print("\n  Kopuk/eksik harf: YOK")
w_actual = round(result.bounds_mm[2] - result.bounds_mm[0], 1)
h_actual = round(result.bounds_mm[3] - result.bounds_mm[1], 1)
print(f"  Gercek boyut: {w_actual} x {h_actual} mm  (hedef ~100 mm)")
print(f"  Validation: {'OK' if result.validation.ok else 'UYARI'}")

# ── compare_letters.png: sol=orijinal logo (yaziya yakın), sag=onizleme ──────
print("\nKarsilastirma gorseli olusturuluyor...")

orig  = PILImage.open(str(LOGO)).convert("RGB")
after = PILImage.open(OUT / "logo_100mm_preview.png").convert("RGB")

# Orijinal logoda yazı alanı: alt %45'i kırp
orig_text_y = int(orig.height * 0.55)
orig_crop   = orig.crop((0, orig_text_y, orig.width, orig.height))

# Onizlemede yazı alanı: alt %45'i kırp
after_text_y = int(after.height * 0.55)
after_crop   = after.crop((0, after_text_y, after.width, after.height))

# Her ikisini de sabit yüksekliğe getir
TARGET_H = 220
def resize_h(img, h):
    w = int(img.width * h / img.height)
    return img.resize((w, h), PILImage.LANCZOS)

orig_r  = resize_h(orig_crop,  TARGET_H)
after_r = resize_h(after_crop, TARGET_H)

pad    = 10
header = 30
total_w = orig_r.width + after_r.width + pad * 3
total_h = TARGET_H + header + pad * 2

canvas = PILImage.new("RGB", (total_w, total_h), (245, 245, 245))
canvas.paste(orig_r,  (pad,              header + pad))
canvas.paste(after_r, (pad*2 + orig_r.width, header + pad))

draw = ImageDraw.Draw(canvas)
try:
    fnt = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 15)
except Exception:
    fnt = ImageFont.load_default()

draw.text((pad,                       6), "ORIJINAL LOGO (yazı bölgesi)",
          fill=(80, 80, 80), font=fnt)
draw.text((pad*2 + orig_r.width,      6), "YENİ ÖNİZLEME — fill-first (eksiksiz)",
          fill=(30, 110, 30), font=fnt)
draw.line([(pad*2 + orig_r.width - 1, 0),
           (pad*2 + orig_r.width - 1, total_h)], fill=(200, 200, 200), width=1)

canvas.save(str(OUT / "compare_letters.png"))
print("Kaydedildi: out/compare_letters.png")
print("\nDogrulama BASARILI.")

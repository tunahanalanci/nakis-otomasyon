"""100mm önizleme + karşılaştırma üret."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image as PILImage
from src.config import Config, FillConfig, SatinConfig, HoopConfig, load
from src.pipeline import run

LOGO = Path("samples/gelin_tekstil_logo.jpg")
OUT  = Path("out"); OUT.mkdir(exist_ok=True)

with PILImage.open(str(LOGO)) as im:
    iw, ih = im.size

cfg = load("config/default.json")
cfg.width_mm     = 100.0
cfg.height_mm    = cfg.width_mm * ih / iw
cfg.max_colors   = 2
cfg.use_inkstitch = False
cfg.fill = FillConfig(spacing_mm=0.4, angle_deg=45, underlay=True)
cfg.satin = SatinConfig(min_width_mm=0.5, max_width_mm=8.0, density_mm=0.4)
cfg.hoop = HoopConfig(w=200, h=200)

print(f"Boyut: {cfg.width_mm:.0f} × {cfg.height_mm:.1f} mm")
result = run(str(LOGO), cfg, "out/preview_100mm_tmp")
print(f"Dikiş: {result.total_stitches}  Renk blok: {result.n_color_blocks}")
print(f"Bounds: {result.bounds_mm}")

import shutil
shutil.copy(result.preview_path, OUT / "logo_100mm_before.png")
print("Kaydedildi: out/logo_100mm_before.png")

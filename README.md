# nakis-otomasyon

PNG görüntüsünden Tajima endüstriyel nakış makinelerinin okuduğu **DST** dosyası üreten Python otomasyon sistemi.

## Özellikler

- PNG + boyut (mm) → DST dosyası
- k-means renk azaltma (ayarlanabilir renk sayısı)
- Otomatik fill / satin / running stitch seçimi
- DST renk taşımadığı için operatör rehberi: **renk sırası raporu** (TXT + swatch PNG)
- Stitch yoğunluğu ve kasnak sınır doğrulaması
- Opsiyonel USB'ye doğrudan kopyalama

## Kurulum

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

## Kullanım

```bash
python cli.py logo.png --width 80 --height 60 --colors 4 --out out/
```

### Tüm seçenekler

```
usage: nakis [-h] [--width MM] [--height MM] [--colors N] [--config PATH] [--out DIR] png

PNG → DST embroidery automation for Tajima industrial machines.

positional arguments:
  png            Input PNG file path

options:
  --width MM     Design width in mm (overrides config)
  --height MM    Design height in mm (overrides config)
  --colors N     Maximum number of thread colours (overrides config)
  --config PATH  JSON config file (default: config/default.json)
  --out DIR      Output directory (default: out/)
```

## Testler

```bash
pytest -q
```

## Faz Yol Haritası

| Faz | Kapsam | Durum |
|-----|--------|-------|
| 0 | İskelet, CI, paket yapısı | ✅ Tamamlandı |
| 1 | Ön işleme: arka plan silme, ölçekleme, gürültü | 🔲 Bekliyor |
| 2 | Renk azaltma (k-means) + palet raporu | 🔲 Bekliyor |
| 3 | Renk maskeleme + vektörizasyon (Shapely) | 🔲 Bekliyor |
| 4 | Fill stitch motoru (tarama + underlay) | 🔲 Bekliyor |
| 5 | Satin stitch motoru (medyal eksen) | 🔲 Bekliyor |
| 6 | Optimizasyon: sıra, jump, trim | 🔲 Bekliyor |
| 7 | DST dışa aktarım (pyembroidery) + doğrulama | 🔲 Bekliyor |
| 8 | Önizleme PNG + USB yazıcı | 🔲 Bekliyor |

## Yapılandırma

`config/default.json` dosyasını düzenleyin veya `--config` ile farklı bir dosya belirtin:

```json
{
  "width_mm": 80.0,
  "height_mm": 60.0,
  "max_colors": 6,
  "hoop": { "w": 200, "h": 200 },
  "fill": { "spacing_mm": 0.4, "angle_deg": 45, "underlay": true },
  "satin": { "min_width_mm": 1.0, "max_width_mm": 8.0, "density_mm": 0.4 },
  "pull_compensation_mm": 0.2,
  "min_stitch_mm": 0.5,
  "trim_jumps": true,
  "output_format": "dst"
}
```

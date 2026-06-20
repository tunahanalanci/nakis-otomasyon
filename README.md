# nakis-otomasyon

PNG görüntüsünden Tajima endüstriyel nakış makinelerinin okuduğu **DST** dosyası üreten Python otomasyon sistemi.

## Ozellikler

- **Web arayuzu** — tarayicidan gorsel yukle, DST indir (`python app.py`)
- PNG / JPG + boyut (mm) → Tajima DST dosyasi
- Tatami dolgu + underlay + satin stitch motoru
- k-means renk azaltma; tek renk logolar dahil tum durumlar
- Beyaz/seffaf arka plan otomatik tespiti; delikler (harf gozleri, yildizlar) dikilmez
- Operatör renk sirasi raporu (TXT)
- Stitch yogunlugu, kasnak siniri, kisa/uzun dikis dogrulamasi
- USB'ye dogrudan kopyalama

> **Tavsiye:** Sade, az renkli logolar en iyi sonucu verir. Fotograf veya degradeli gorseller nakis icin uygun degildir.

## Kurulum

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

## Web Arayuzu (Onerilen)

```bash
python app.py
```

Tarayici otomatik acar: `http://localhost:5000`

- Gorsel surukle-birak yukle
- Genislik / yukseklik (mm) gir
- Kasnak boyutu sec, renk ve gelismis ayarlar
- **DST Uret** butonuna tikla
- Onizlemeyi gor, DST + renk raporu indir

## Komut Satiri

```bash
python cli.py logo.png --width 80 --height 60 --colors 4 --out out/
```

USB'ye otomatik kopyalama:

```bash
python cli.py logo.png --width 80 --height 60 --out out/ --usb E:\\ --usb-layout EMB
```

### Tüm seçenekler

```
usage: nakis [-h] [--width MM] [--height MM] [--colors N] [--config PATH]
             [--out DIR] [--usb PATH] [--usb-layout LAYOUT] [--debug] png

positional arguments:
  png                  Input PNG file path

options:
  --width MM           Design width in mm (overrides config)
  --height MM          Design height in mm (overrides config)
  --colors N           Maximum number of thread colours (overrides config)
  --config PATH        JSON config file (default: config/default.json)
  --out DIR            Output directory (default: out/)
  --usb PATH           USB drive root path; copies DST + report + preview
  --usb-layout LAYOUT  'root' = USB root, any other string = subdirectory
                       (e.g. 'PATTERN', 'EMB'). Default: root
  --debug              Save intermediate colour-reduced PNG to --out
```

### Çıktılar

| Dosya | Açıklama |
|-------|----------|
| `out/<isim>.dst` | Tajima DST dosyası |
| `out/<isim>_preview.png` | Dikiş yolu önizlemesi |
| `out/renk_sirasi.txt` | Renk sırası raporu (operatör kılavuzu) |

## Ink/Stitch Motoru (feat/inkstitch-engine)

Mevcut el yazımı stitch motoruna alternatif olarak **Inkscape + Ink/Stitch** tabanlı motor.

### Kurulum

1. **Inkscape 1.4+** kur (Windows MSI: https://inkscape.org/release/ )
2. **Ink/Stitch** eklentisini kullanıcı extensions klasörüne kur:
   ```powershell
   # Ink/Stitch v3.2.2 zip'i indir
   Invoke-WebRequest -Uri "https://github.com/inkstitch/inkstitch/releases/download/v3.2.2/inkstitch-v3.2.2-windows-64bit.zip" `
     -OutFile "$env:TEMP\inkstitch.zip"
   # Kullanici extensions klasorune cikart
   Expand-Archive "$env:TEMP\inkstitch.zip" "$env:APPDATA\inkscape\extensions" -Force
   ```

### Headless DST export (komut satırı)

```powershell
inkscape --batch-process `
  "--actions=select-all;org.inkstitch.output.dst;export-filename:out.dst;export-do" `
  input.svg
```

### POC testi

```bash
python scripts/inkstitch_poc.py
# Cikti: out/poc.dst, out/poc_preview.png
```

### Logo isleme

```bash
python scripts/inkstitch_logo.py
# Cikti: out/logo_inkstitch.dst, out/logo_inkstitch_preview.png
```

### Motor ciktisini goster

```bash
python scripts/show_engine_output.py
# Cikti: out/logo_inkstitch_preview.png (bilgi seridi), out/compare_logo.png,
#        out/logo_process.gif, out/logo_test_80mm.dst, out/renk_sirasi.txt
```

### Makinede test (Tajima)

1. `out/logo_test_80mm.dst` dosyasini FAT32 USB belleğe kopyala
2. Tajima'da aç ve renk sirasini `out/renk_sirasi.txt`'ye gore iplik ata:
   - 1. ilik → **Lacivert** (#2b3b4a)
   - 2. ilik → **Altın** (#aa8a50)
3. Dik; aşağıdakileri not et:

| Kontrol | Sonuç |
|---|---|
| USB'de dosya klasörü/adı | |
| Gerçek boyut (cetvelle ölç mm) | |
| Dolgu kalitesi | |
| Renk durması çalışıyor mu? | |

## Testler

```bash
pytest -q
```

## Faz Yol Haritası

| Faz | Kapsam | Durum |
|-----|--------|-------|
| 0 | İskelet, CI, paket yapısı | ✅ Tamamlandı |
| 1 | Ön işleme: arka plan silme, ölçekleme, gürültü | ✅ Tamamlandı |
| 2 | Renk azaltma (k-means) + palet raporu | ✅ Tamamlandı |
| 3 | Renk maskeleme + vektörizasyon (Shapely) | ✅ Tamamlandı |
| 4 | Fill stitch motoru (tarama + underlay) | ✅ Tamamlandı |
| 5 | Satin stitch motoru (medyal eksen) | ✅ Tamamlandı |
| 6 | Optimizasyon: sıra, jump, trim | ✅ Tamamlandı |
| 7 | DST dışa aktarım (pyembroidery) + doğrulama | ✅ Tamamlandı |
| 8 | Önizleme PNG + USB yazıcı | ✅ Tamamlandı |

## Faz 0: USB Testi (Tajima Makine Doğrulaması)

Bu adım, pipeline tamamlanmadan önce makineyi ve iş akışını bilinen bir geometriyle doğrular.

### 1. Test dosyasını üret

```bash
python scripts/make_test_dst.py
```

Konsol çıktısı:
```
Dikis sayisi : 162
Renk degisimi: 1  (2 blok)
Sinirlar     : 40.0 x 40.0 mm
```

`out/test_kare.dst` ve `out/test_kare.png` oluşur.
PNG'yi açarak deseni görsel olarak doğrula: dış çerçeve siyah koşu dikiş, iç dolu kare kırmızı tatami dolgu olmalı.

### 2. USB'ye kopyala

DST dosyasını FAT32 formatlı USB belleğe kopyala.
Tajima modeline göre beklenen klasör/isim yapısı:

| Model ailesi | USB klasörü | Dosya adı kuralı |
|---|---|---|
| TFMX / TMEX | Kök dizin (`/`) | 8.3 format (örn. `TEST_KAR.DST`) |
| TME-SC / TME-DC | `/DESIGN/` | Uzun isim desteklenir |
| SAI serisi | `/EMB/` | `.DST` uzantısı zorunlu |

> **Not:** Makineni test ettikten sonra hangi klasörde ve hangi isimle göründüğünü buraya yaz — USB yerleşimi modele göre değişir ve ilerideki `usb_writer.py` implementasyonunda kullanılacak.

### 3. Makine kontrolü

Makineyi kasnak boyutuna göre ayarla (en az 50×50 mm kasnak önerilir).
Dosyayı yükle ve **gerçekten dik**. Aşağıdakileri doğrula:

- [ ] Çerçeve boyutu doğru: 40×40 mm
- [ ] Dolgu boyutu doğru: 20×20 mm (çerçeve ortasında)
- [ ] Renk değişimi: makine 1. iplikten sonra durup operatörü bekliyor mu?
- [ ] Dolgu dikiş yoğunluğu kabul edilebilir (kumaşta kıvrılma yok)
- [ ] Başlangıç/bitiş ipliği güvenli; atlamalar minimal

Makine testi sonuçlarını bu tabloya kaydet:

| Kontrol | Sonuç |
|---|---|
| Gerçek çerçeve boyutu (cetvelle ölç) | ___ × ___ mm |
| Dolgu kalitesi | |
| Renk durması çalışıyor mu? | |
| USB'de görünen klasör/dosya adı | |
| Toplam dikiş süresi (sn) | |

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

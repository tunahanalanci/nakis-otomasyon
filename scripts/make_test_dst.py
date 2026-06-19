#!/usr/bin/env python3
"""
Faz-0 test generator: bilinen geometri ile gerçek Tajima makine testi için
minimal DST ve PNG önizlemesi üretir.

Desen:
  Blok 0 (siyah iplik) : 40x40 mm kare çerçeve — koşu dikiş, 2.5 mm aralık.
  Blok 1 (kırmızı iplik): 20x20 mm dolu kare — tatami dolgu, 2 mm satır aralığı.

DST birimi = 0.1 mm  →  1 mm = 10 birim.

Kullanim:
    python scripts/make_test_dst.py

Cikti:
    out/test_kare.dst   — makineye yuklenecek dosya
    out/test_kare.png   — dikiş önizlemesi
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pyembroidery
from PIL import Image, ImageDraw

# ── Yollar ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / "out"
OUT.mkdir(exist_ok=True)

DST_OUT = OUT / "test_kare.dst"
PNG_OUT = OUT / "test_kare.png"

# ── Sabitler (DST birimi = 0.1 mm) ───────────────────────────────────────────
FRAME_HALF = 200   # çerçeve yarı kenarı → 40×40 mm
FILL_HALF  = 100   # dolgu yarı kenarı   → 20×20 mm
RUN_SPACE  = 25    # koşu dikiş aralığı  → 2.5 mm
FILL_ROWS  = 20    # tatami satır aralığı → 2.0 mm
FILL_SPACE = 25    # satır içi dikiş aralığı → 2.5 mm

# Önizleme renkleri: [blok-0, blok-1, atlama]
BLOCK_COLOURS = ["#1a1a1a", "#cc3333"]
JUMP_COLOUR   = "#cccccc"
PX_PER_UNIT   = 3    # görsel büyütme faktörü
CANVAS_PAD    = 80   # piksel kenar boşluğu


# ── Yardımcı ─────────────────────────────────────────────────────────────────

def line_pts(
    x1: float, y1: float,
    x2: float, y2: float,
    spacing: float,
) -> list[tuple[int, int]]:
    """(x1,y1)→(x2,y2) doğrusu üzerinde eşit aralıklı nokta listesi döndürür."""
    dx, dy = x2 - x1, y2 - y1
    n = max(1, round(math.hypot(dx, dy) / spacing))
    return [
        (round(x1 + dx * i / n), round(y1 + dy * i / n))
        for i in range(n + 1)
    ]


# ── Desen üretici ─────────────────────────────────────────────────────────────

def build_pattern() -> pyembroidery.EmbPattern:
    """Her iki bloğu içeren EmbPattern döndürür."""
    p = pyembroidery.EmbPattern()

    # İplik meta verisi (DST'de renk taşınmaz; makine yok sayar)
    p.add_thread({"color": 0x111111, "name": "Black"})
    p.add_thread({"color": 0xCC3333, "name": "Red"})

    # ── Blok 0: 40×40 mm çerçeve (koşu dikiş) ────────────────────────────────
    H = FRAME_HALF
    corners = [(-H, -H), (H, -H), (H, H), (-H, H), (-H, -H)]

    # İğneyi başlangıca taşı (dikiş yok)
    p.add_stitch_absolute(pyembroidery.JUMP, *corners[0])

    for i in range(4):
        seg = line_pts(*corners[i], *corners[i + 1], RUN_SPACE)
        for x, y in seg[1:]:              # ilk nokta bir önceki stitch'te zaten
            p.add_stitch_absolute(pyembroidery.STITCH, x, y)

    # ── Renk değişimi ─────────────────────────────────────────────────────────
    # COLOR_BREAK: kes + dur, operatör ipliği değiştirir
    p.add_stitch_absolute(pyembroidery.COLOR_BREAK, *corners[-1])

    # ── Blok 1: 20×20 mm tatami dolgu ────────────────────────────────────────
    F  = FILL_HALF
    ys = range(-F, F + 1, FILL_ROWS)          # -100 … +100, 11 satır

    for row_idx, y in enumerate(ys):
        x0, x1 = (-F, F) if row_idx % 2 == 0 else (F, -F)   # gidip-dön
        row_pts = line_pts(x0, y, x1, y, FILL_SPACE)

        for j, (x, _) in enumerate(row_pts):
            # İlk satırın ilk noktasına JUMP ile git; geri kalan hepsi STITCH
            cmd = pyembroidery.JUMP if (row_idx == 0 and j == 0) \
                  else pyembroidery.STITCH
            p.add_stitch_absolute(cmd, x, y)

    p.add_stitch_absolute(pyembroidery.END, 0, 0)
    return p


# ── Dışa aktarım ─────────────────────────────────────────────────────────────

def save_dst(p: pyembroidery.EmbPattern) -> None:
    """Deseni Tajima DST olarak yazar."""
    pyembroidery.write(p, str(DST_OUT))


def save_png(p: pyembroidery.EmbPattern) -> None:
    """Her bloğu ayrı renkte rasterize ederek PNG önizlemesi oluşturur."""
    drawable = [
        (s[0], s[1], s[2]) for s in p.stitches
        if s[2] in (pyembroidery.STITCH, pyembroidery.JUMP)
    ]
    if not drawable:
        print("UYARI: çizilecek dikiş bulunamadı.", file=sys.stderr)
        return

    xs = [d[0] for d in drawable]
    ys = [d[1] for d in drawable]
    min_x, min_y = min(xs), min(ys)
    max_x, max_y = max(xs), max(ys)

    W = round((max_x - min_x) * PX_PER_UNIT) + 2 * CANVAS_PAD
    H = round((max_y - min_y) * PX_PER_UNIT) + 2 * CANVAS_PAD

    img  = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    def to_px(x: float, y: float) -> tuple[int, int]:
        return (
            round((x - min_x) * PX_PER_UNIT) + CANVAS_PAD,
            round((y - min_y) * PX_PER_UNIT) + CANVAS_PAD,
        )

    block = 0
    prev: tuple[int, int] | None = None

    for s in p.stitches:
        x, y, cmd = s[0], s[1], s[2]

        if cmd == pyembroidery.COLOR_BREAK:
            block += 1
            prev = None
            continue

        if cmd == pyembroidery.END:
            break

        cur = to_px(x, y)

        if cmd == pyembroidery.STITCH and prev is not None:
            colour = BLOCK_COLOURS[min(block, len(BLOCK_COLOURS) - 1)]
            draw.line([prev, cur], fill=colour, width=2)
        elif cmd == pyembroidery.JUMP and prev is not None:
            draw.line([prev, cur], fill=JUMP_COLOUR, width=1)

        prev = cur

    img.save(str(PNG_OUT))


# ── Rapor ─────────────────────────────────────────────────────────────────────

def report(p: pyembroidery.EmbPattern) -> None:
    """Konsola dikiş sayısı, renk değişimi ve tasarım sınırlarını yazar."""
    stitches = [s for s in p.stitches if s[2] == pyembroidery.STITCH]
    breaks   = [s for s in p.stitches if s[2] == pyembroidery.COLOR_BREAK]

    xs = [s[0] for s in stitches]
    ys = [s[1] for s in stitches]
    if xs:
        w_mm = (max(xs) - min(xs)) / 10
        h_mm = (max(ys) - min(ys)) / 10
    else:
        w_mm = h_mm = 0.0

    sep = "-" * 45
    print(sep)
    print(f"  DST          : {DST_OUT.relative_to(ROOT)}")
    print(f"  Onizleme PNG : {PNG_OUT.relative_to(ROOT)}")
    print(f"  Dikis sayisi : {len(stitches)}")
    print(f"  Renk degisimi: {len(breaks)}  ({len(breaks) + 1} blok)")
    print(f"  Sinirlar     : {w_mm:.1f} x {h_mm:.1f} mm")
    print(sep)
    print("Tajima makinesine yuklemek icin out/test_kare.dst dosyasini USB'ye kopyalayin.")


# ── Ana giriş ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Desen uretiliyor...")
    pat = build_pattern()
    save_dst(pat)
    save_png(pat)
    report(pat)

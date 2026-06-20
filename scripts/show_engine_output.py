"""
show_engine_output.py — Gorev: motorun ciktisini goster ve dogrula

Uretilen dosyalar:
  out/logo_inkstitch_preview.png   — bilgi seridi ekli yuksek cozunurluk preview
  out/poc_preview.png              — POC yuksek cozunurluk preview
  out/compare_logo.png             — orijinal vs Ink/Stitch yan yana
  out/logo_process.gif             — dikis sirasi animasyonu
  out/logo_test_80mm.dst           — 80mm genislikte makine testi DST
  out/renk_sirasi.txt              — operator renk atama kilavuzu
"""

from __future__ import annotations

import math
import subprocess
import sys
import re
from pathlib import Path

import pyembroidery
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "out"
SAMPLES = ROOT / "samples"
INKSCAPE = r"C:\Program Files\Inkscape\bin\inkscape.exe"

# Renk paleti (DST'deki siralama: 0=lacivert, 1=altin)
THREAD_COLORS = [
    {"hex": "#2b3b4a", "rgb": (43, 59, 74),   "ad": "Lacivert"},
    {"hex": "#aa8a50", "rgb": (170, 138, 80),  "ad": "Altin"},
]


# ── Yardimci: DST oku ─────────────────────────────────────────────────────────

def load_dst(path: Path):
    pat = pyembroidery.read(str(path))
    stitches = pat.stitches
    stitch_pts = [(s[0], s[1]) for s in stitches if s[2] == pyembroidery.STITCH]
    color_changes = sum(1 for s in stitches if s[2] == pyembroidery.COLOR_CHANGE)
    xs = [p[0] for p in stitch_pts]
    ys = [p[1] for p in stitch_pts]
    stats = {
        "stitch_count": len(stitch_pts),
        "color_blocks": color_changes + 1,
        "w_mm": (max(xs) - min(xs)) / 10 if xs else 0,
        "h_mm": (max(ys) - min(ys)) / 10 if ys else 0,
        "min_x": min(xs) if xs else 0,
        "min_y": min(ys) if ys else 0,
        "max_x": max(xs) if xs else 0,
        "max_y": max(ys) if ys else 0,
    }
    return pat, stats


# ── 1. Yuksek cozunurluk preview + bilgi seridi ───────────────────────────────

def render_preview_with_info(dst_path: Path, out_path: Path,
                              scale: float = 6.0, pad: int = 30) -> None:
    pat, stats = load_dst(dst_path)
    stitches = pat.stitches
    min_x = stats["min_x"]
    min_y = stats["min_y"]
    w = int(stats["w_mm"] * scale / 10 * 10) + 2 * pad
    h = int(stats["h_mm"] * scale / 10 * 10) + 2 * pad

    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    color_idx = 0
    prev = None
    for x, y, cmd in stitches:
        if cmd == pyembroidery.COLOR_CHANGE:
            color_idx = min(color_idx + 1, len(THREAD_COLORS) - 1)
            prev = None
            continue
        if cmd in (pyembroidery.TRIM, pyembroidery.JUMP):
            prev = None
            continue
        if cmd == pyembroidery.STITCH:
            px = int((x - min_x) * scale / 10) + pad
            py = int((y - min_y) * scale / 10) + pad
            col = THREAD_COLORS[color_idx]["rgb"]
            if prev:
                draw.line([prev, (px, py)], fill=col, width=1)
            prev = (px, py)

    # Bilgi seridi (uste ekle)
    bar_h = 60
    bar = Image.new("RGB", (w, bar_h), (30, 30, 30))
    bd = ImageDraw.Draw(bar)

    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)
        font_sm = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
    except Exception:
        font = font_sm = ImageFont.load_default()

    info = (f"Boyut: {stats['w_mm']:.1f} x {stats['h_mm']:.1f} mm  |  "
            f"Dikis: {stats['stitch_count']:,}  |  "
            f"Renk blogu: {stats['color_blocks']}")
    bd.text((10, 8), info, fill=(255, 255, 255), font=font)

    # Renk kareleri
    x_cur = 10
    for i, tc in enumerate(THREAD_COLORS[:stats["color_blocks"]]):
        bd.rectangle([x_cur, 32, x_cur + 16, 48], fill=tc["rgb"])
        bd.text((x_cur + 20, 32), f"{i+1}. {tc['ad']} {tc['hex']}", fill=(220, 220, 220), font=font_sm)
        x_cur += 160

    final = Image.new("RGB", (w, bar_h + h), (255, 255, 255))
    final.paste(bar, (0, 0))
    final.paste(img, (0, bar_h))
    final.save(str(out_path))
    print(f"[show] Preview kaydedildi: {out_path}")


def render_poc_preview(dst_path: Path, out_path: Path,
                       scale: float = 6.0, pad: int = 30) -> None:
    pat, stats = load_dst(dst_path)
    stitches = pat.stitches
    min_x = stats["min_x"]
    min_y = stats["min_y"]
    w = int(stats["w_mm"] * scale / 10 * 10) + 2 * pad
    h = int(stats["h_mm"] * scale / 10 * 10) + 2 * pad
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    poc_colors = [(26, 58, 110), (168, 135, 75)]
    color_idx = 0
    prev = None
    for x, y, cmd in stitches:
        if cmd == pyembroidery.COLOR_CHANGE:
            color_idx = min(color_idx + 1, len(poc_colors) - 1)
            prev = None
            continue
        if cmd in (pyembroidery.TRIM, pyembroidery.JUMP):
            prev = None
            continue
        if cmd == pyembroidery.STITCH:
            px = int((x - min_x) * scale / 10) + pad
            py = int((y - min_y) * scale / 10) + pad
            if prev:
                draw.line([prev, (px, py)], fill=poc_colors[color_idx], width=1)
            prev = (px, py)
    img.save(str(out_path))
    print(f"[show] POC preview kaydedildi: {out_path}")


# ── 2. Karsilastirma gorseli ──────────────────────────────────────────────────

def build_compare(logo_path: Path, preview_path: Path, out_path: Path) -> None:
    orig = Image.open(str(logo_path)).convert("RGB")
    prev = Image.open(str(preview_path)).convert("RGB")

    # Esit yukseklikte yeniden boyutlandir
    target_h = 500
    orig_w = int(orig.width * target_h / orig.height)
    prev_w = int(prev.width * target_h / prev.height)
    orig = orig.resize((orig_w, target_h), Image.LANCZOS)
    prev = prev.resize((prev_w, target_h), Image.LANCZOS)

    gap = 20
    label_h = 30
    total_w = orig_w + prev_w + gap
    total_h = target_h + label_h

    canvas = Image.new("RGB", (total_w, total_h), (240, 240, 240))

    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(canvas)
    draw.text((orig_w // 2 - 40, 5), "Orijinal Logo", fill=(50, 50, 50), font=font)
    draw.text((orig_w + gap + prev_w // 2 - 60, 5), "Ink/Stitch Onizleme", fill=(50, 50, 50), font=font)

    canvas.paste(orig, (0, label_h))
    canvas.paste(prev, (orig_w + gap, label_h))

    canvas.save(str(out_path))
    print(f"[show] Karsilastirma kaydedildi: {out_path}")


# ── 3. GIF animasyonu ─────────────────────────────────────────────────────────

def build_gif(dst_path: Path, out_path: Path,
              n_frames: int = 200, scale: float = 4.0, pad: int = 20) -> None:
    pat, stats = load_dst(dst_path)
    stitches = pat.stitches
    min_x = stats["min_x"]
    min_y = stats["min_y"]
    w = int(stats["w_mm"] * scale / 10 * 10) + 2 * pad
    h = int(stats["h_mm"] * scale / 10 * 10) + 2 * pad

    # Sadece stitch+color_change komutlarini filtrele (animasyon icin)
    draw_cmds = [s for s in stitches
                 if s[2] in (pyembroidery.STITCH, pyembroidery.COLOR_CHANGE,
                              pyembroidery.TRIM, pyembroidery.JUMP)]

    # Kare basina kac stitch?
    total_stitches = stats["stitch_count"]
    step = max(1, total_stitches // n_frames)

    frames = []
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    color_idx = 0
    prev = None
    drawn = 0
    frame_counter = 0

    for x, y, cmd in draw_cmds:
        if cmd == pyembroidery.COLOR_CHANGE:
            color_idx = min(color_idx + 1, len(THREAD_COLORS) - 1)
            prev = None
            continue
        if cmd in (pyembroidery.TRIM, pyembroidery.JUMP):
            prev = None
            continue
        if cmd == pyembroidery.STITCH:
            px = int((x - min_x) * scale / 10) + pad
            py = int((y - min_y) * scale / 10) + pad
            col = THREAD_COLORS[color_idx]["rgb"]
            if prev:
                draw.line([prev, (px, py)], fill=col, width=1)
            prev = (px, py)
            drawn += 1
            if drawn % step == 0:
                frames.append(img.copy())
                frame_counter += 1

    # Son kare
    frames.append(img.copy())

    if not frames:
        print("[show] GIF: frame yok")
        return

    # Optimize: her 2. kareyi atla (boyut azalt)
    if len(frames) > 150:
        frames = frames[::2]

    frames[0].save(
        str(out_path),
        save_all=True,
        append_images=frames[1:],
        duration=40,
        loop=0,
        optimize=True,
    )
    print(f"[show] GIF kaydedildi: {out_path} ({len(frames)} kare)")


# ── 4. 80mm DST ──────────────────────────────────────────────────────────────

def build_80mm_dst() -> None:
    """Logo SVG'yi 80mm genislikte yeniden export et."""
    src_svg = OUT / "logo_inkstitch.svg"
    dst_80  = OUT / "logo_test_80mm.dst"
    svg_80  = OUT / "logo_inkstitch_80mm.svg"

    # Mevcut SVG boyutunu oku
    content = src_svg.read_text(encoding="utf-8")

    # viewBox degerini bul
    vb_match = re.search(r'viewBox="([^"]+)"', content)
    w_match  = re.search(r'width="([\d.]+)mm"', content)
    h_match  = re.search(r'height="([\d.]+)mm"', content)

    if not (vb_match and w_match and h_match):
        print("[show] SVG boyutu okunamadi, atlaniyor")
        return

    orig_w = float(w_match.group(1))
    orig_h = float(h_match.group(1))
    scale_factor = 80.0 / orig_w
    new_h = round(orig_h * scale_factor, 2)

    # SVG'yi 80mm olarak guncelle
    new_content = content
    new_content = re.sub(r'width="[\d.]+mm"', f'width="80mm"', new_content)
    new_content = re.sub(r'height="[\d.]+mm"', f'height="{new_h}mm"', new_content)

    # viewBox'i da guncelle (px birimi mm ile esles)
    vb_parts = vb_match.group(1).split()
    if len(vb_parts) == 4:
        new_vb = f"{vb_parts[0]} {vb_parts[1]} 80 {new_h}"
        new_content = new_content.replace(vb_match.group(0), f'viewBox="{new_vb}"')

    svg_80.write_text(new_content, encoding="utf-8")

    # Inkscape ile DST export
    actions = f"select-all;org.inkstitch.output.dst;export-filename:{dst_80};export-do"
    cmd = [INKSCAPE, "--batch-process", f"--actions={actions}", str(svg_80)]
    print("[show] 80mm DST export ediliyor...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if dst_80.exists() and dst_80.stat().st_size > 100:
        pat, stats = load_dst(dst_80)
        print(f"[show] logo_test_80mm.dst OK")
        print(f"  Boyut    : {stats['w_mm']:.1f} x {stats['h_mm']:.1f} mm")
        print(f"  Dikis    : {stats['stitch_count']:,}")
        print(f"  Renkler  : {stats['color_blocks']} blok")
    else:
        print(f"[show] 80mm DST basarisiz (exit={r.returncode})")
        if r.stderr:
            print(r.stderr[:300])


# ── 5. Renk sirasi raporu ─────────────────────────────────────────────────────

def write_color_report(dst_path: Path, out_path: Path) -> None:
    pat, stats = load_dst(dst_path)
    lines = [
        "RENK SIRASI RAPORU — Gelin Tekstil Logo",
        f"Dosya  : {dst_path.name}",
        f"Boyut  : {stats['w_mm']:.1f} x {stats['h_mm']:.1f} mm",
        f"Dikis  : {stats['stitch_count']:,}",
        "",
        "IPLIK SIRASI:",
        "-" * 40,
    ]
    for i, tc in enumerate(THREAD_COLORS[:stats["color_blocks"]], start=1):
        lines.append(f"  {i}. {tc['ad']:12s}  {tc['hex']}  RGB({tc['rgb'][0]},{tc['rgb'][1]},{tc['rgb'][2]})")

    lines += [
        "-" * 40,
        "",
        "NOT: Makine her renk blogu sonunda durur.",
        "Operator iplik degerini yukardaki siraya gore atar.",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[show] Renk raporu: {out_path}")
    for ln in lines:
        print("  " + ln)


# ── Ana akis ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logo_dst  = OUT / "logo_inkstitch.dst"
    poc_dst   = OUT / "poc.dst"
    logo_prev = OUT / "logo_inkstitch_preview.png"
    poc_prev  = OUT / "poc_preview.png"
    compare   = OUT / "compare_logo.png"
    gif_path  = OUT / "logo_process.gif"
    renk_txt  = OUT / "renk_sirasi.txt"

    print("=== 1. Yuksek cozunurluk preview ===")
    render_preview_with_info(logo_dst, logo_prev)
    render_poc_preview(poc_dst, poc_prev)

    print("\n=== 2. Karsilastirma gorseli ===")
    build_compare(SAMPLES / "gelin_tekstil_logo.jpg", logo_prev, compare)

    print("\n=== 3. GIF animasyonu ===")
    build_gif(logo_dst, gif_path)

    print("\n=== 4. 80mm DST ===")
    build_80mm_dst()

    print("\n=== 5. Renk raporu ===")
    write_color_report(OUT / "logo_test_80mm.dst", renk_txt)

    print("\n=== TAMAMLANDI ===")
    print(f"  {logo_prev}")
    print(f"  {poc_prev}")
    print(f"  {compare}")
    print(f"  {gif_path}")
    print(f"  {OUT / 'logo_test_80mm.dst'}")
    print(f"  {renk_txt}")

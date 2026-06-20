"""Colour quantisation: reduce image palette to max_colors using k-means."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from sklearn.cluster import KMeans

from src.config import Config

_ALPHA_FG_THRESH: int = 127  # pixels with alpha > this are foreground
_BG_BRIGHT_THRESH: int = 240  # RGB pixels with all channels > this = near-white background


def quantise(
    img: np.ndarray,
    cfg: Config,
) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    """Reduce *img* to at most cfg.max_colors using k-means on foreground pixels.

    Parameters
    ----------
    img:
        HxWx3 (RGB) or HxWx4 (RGBA) uint8 array.
        When RGBA, pixels with alpha <= _ALPHA_FG_THRESH are treated as
        background and excluded from clustering.

    Returns
    -------
    label_map : HxW int32 array.  Values 0..n-1 for foreground pixels (sorted by
                descending cluster size so 0 = dominant colour), -1 for background.
    palette   : list of (R, G, B) int tuples in the same descending-size order.
    """
    h, w = img.shape[:2]

    if img.ndim == 3 and img.shape[2] == 4:
        fg_mask = img[:, :, 3] > _ALPHA_FG_THRESH
        rgb     = img[:, :, :3]
    else:
        rgb     = img[:, :, :3]
        # Treat near-white pixels (all channels > threshold) as background
        fg_mask = ~np.all(rgb > _BG_BRIGHT_THRESH, axis=2)

    fg_pixels  = rgb[fg_mask].astype(np.float32)
    n_clusters = min(cfg.max_colors, len(fg_pixels))

    if n_clusters < 1:
        return np.full((h, w), -1, dtype=np.int32), []

    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    km.fit(fg_pixels)

    # Sort clusters by descending pixel count: colour 0 = most common colour
    counts = np.bincount(km.labels_.astype(np.int64), minlength=n_clusters)
    order  = np.argsort(-counts)                   # order[new_idx] = old_cluster
    remap  = np.empty(n_clusters, dtype=np.int32)
    remap[order] = np.arange(n_clusters)           # remap[old] = new

    palette: list[tuple[int, int, int]] = [
        (
            int(km.cluster_centers_[order[i]][0]),
            int(km.cluster_centers_[order[i]][1]),
            int(km.cluster_centers_[order[i]][2]),
        )
        for i in range(n_clusters)
    ]

    label_map = np.full((h, w), -1, dtype=np.int32)
    label_map[fg_mask] = remap[km.labels_]
    return label_map, palette


def build_color_report(
    palette: list[tuple[int, int, int]],
    out_path: str | Path,
) -> None:
    """Write a thread-order report as a plain-text file and a swatch PNG.

    DST carries no colour data; the operator must load threads in the order
    listed here.  The swatch PNG provides a quick visual reference.

    TODO: map each RGB to the nearest Madeira / Robison-Anton thread name/number.
    """
    out_path = Path(out_path).with_suffix("")   # normalise: strip any extension

    # ── Text report ───────────────────────────────────────────────────────────
    txt_path = out_path.with_suffix(".txt")
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    with txt_path.open("w", encoding="utf-8") as fh:
        fh.write("RENK SIRASI RAPORU\n")
        fh.write("=" * 36 + "\n")
        fh.write("DST renk tasimaz.\n")
        fh.write("Operatoer asagidaki sirada iplik takip etmelidir:\n\n")
        for i, (r, g, b) in enumerate(palette, start=1):
            fh.write(f"  {i:2d}. #{r:02X}{g:02X}{b:02X}  "
                     f"R={r:3d} G={g:3d} B={b:3d}\n")

    # ── Swatch PNG ────────────────────────────────────────────────────────────
    sw_w, sw_h = 80, 60
    label_h    = 18
    margin     = 12
    n          = len(palette)
    img_w      = margin + n * (sw_w + margin)
    img_h      = margin + sw_h + label_h + margin

    canvas = Image.new("RGB", (img_w, img_h), "white")
    draw   = ImageDraw.Draw(canvas)

    for i, (r, g, b) in enumerate(palette):
        x = margin + i * (sw_w + margin)
        y = margin
        draw.rectangle([x, y, x + sw_w - 1, y + sw_h - 1], fill=(r, g, b))
        draw.text((x, y + sw_h + 2), f"{i + 1}. #{r:02X}{g:02X}{b:02X}", fill="black")

    canvas.save(str(out_path.with_suffix(".png")))

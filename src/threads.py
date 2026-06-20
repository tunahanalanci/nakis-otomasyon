"""Thread catalog loading and Lab-based color matching."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "threads"
_DEFAULT_CATALOG = "isacord.json"


@dataclass
class ThreadMatch:
    found_rgb:   tuple[int, int, int]
    thread_code: str
    thread_name: str
    thread_rgb:  tuple[int, int, int]
    delta_e:     float   # Lab Euclidean distance


# ── sRGB → CIE Lab (D65 illuminant) ──────────────────────────────────────────

def _linearize(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_lab(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert sRGB (0-255) to CIE L*a*b* (D65)."""
    rl = _linearize(r / 255.0)
    gl = _linearize(g / 255.0)
    bl = _linearize(b / 255.0)

    X = 0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl
    Y = 0.2126729 * rl + 0.7151522 * gl + 0.0721750 * bl
    Z = 0.0193339 * rl + 0.1191920 * gl + 0.9503041 * bl

    Xn, Yn, Zn = 0.95047, 1.00000, 1.08883

    def f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0

    L = 116.0 * f(Y / Yn) - 16.0
    a = 500.0 * (f(X / Xn) - f(Y / Yn))
    b_val = 200.0 * (f(Y / Yn) - f(Z / Zn))
    return L, a, b_val


# ── Catalog loading ───────────────────────────────────────────────────────────

def load_catalog(brand: str = _DEFAULT_CATALOG) -> list[dict]:
    """Load a thread catalog JSON from data/threads/."""
    path = _DATA_DIR / brand
    if not path.exists():
        path = _DATA_DIR / _DEFAULT_CATALOG
    return json.loads(path.read_text(encoding="utf-8"))


# ── Matching ──────────────────────────────────────────────────────────────────

def _build_lab_array(catalog: list[dict]) -> np.ndarray:
    """Pre-compute Lab values for all catalog entries (N x 3)."""
    rows = []
    for entry in catalog:
        r, g, b = entry["rgb"]
        rows.append(rgb_to_lab(r, g, b))
    return np.array(rows, dtype=np.float64)


def match_palette(
    palette: list[tuple[int, int, int]],
    brand: str = _DEFAULT_CATALOG,
) -> list[ThreadMatch]:
    """Match each palette color to the nearest thread in the catalog.

    Distance metric: Euclidean in CIE L*a*b* space (approx. CIEDE2000).
    """
    catalog = load_catalog(brand)
    lab_catalog = _build_lab_array(catalog)

    results = []
    for r, g, b in palette:
        query = np.array(rgb_to_lab(r, g, b), dtype=np.float64)
        dists = np.sqrt(np.sum((lab_catalog - query) ** 2, axis=1))
        idx = int(np.argmin(dists))
        entry = catalog[idx]
        tr, tg, tb = entry["rgb"]
        results.append(ThreadMatch(
            found_rgb   = (r, g, b),
            thread_code = entry["code"],
            thread_name = entry["name"],
            thread_rgb  = (tr, tg, tb),
            delta_e     = float(dists[idx]),
        ))
    return results


# ── Color report ──────────────────────────────────────────────────────────────

def write_color_report(
    matches: list[ThreadMatch],
    out_path: Path,
    *,
    also_json: bool = True,
) -> None:
    """Write operator-facing renk_sirasi.txt (and optional .json)."""
    lines = [
        "RENK SIRASI RAPORU",
        "=" * 50,
        "",
        "IPLIK SIRASI (makinede ilik atama sirasi):",
        "-" * 50,
    ]
    for i, m in enumerate(matches, start=1):
        r, g, b = m.found_rgb
        tr, tg, tb = m.thread_rgb
        lines += [
            f"  {i}. {m.thread_name} [{m.thread_code}]",
            f"     Bulunan renk : #{r:02x}{g:02x}{b:02x}  RGB({r},{g},{b})",
            f"     Iplik rengi  : #{tr:02x}{tg:02x}{tb:02x}  RGB({tr},{tg},{tb})",
            f"     Delta-E (Lab): {m.delta_e:.1f}",
            "",
        ]
    lines += [
        "-" * 50,
        "NOT: Makine her renk blogu sonunda durur.",
        "Operator iplik degerini yukardaki siraya gore atar.",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")

    if also_json:
        import json as _json
        data = [
            {
                "sira": i,
                "iplik_kodu": m.thread_code,
                "iplik_adi":  m.thread_name,
                "bulunan_hex": "#{:02x}{:02x}{:02x}".format(*m.found_rgb),
                "iplik_hex":   "#{:02x}{:02x}{:02x}".format(*m.thread_rgb),
                "delta_e":     round(m.delta_e, 1),
            }
            for i, m in enumerate(matches, start=1)
        ]
        json_path = out_path.with_suffix(".json")
        json_path.write_text(_json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")
